"""Context builder for enriching task delegations with relevant HexMem data."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional
from .shared_memory import _connect, _canonical


def build_task_context(
    description: str,
    task_type: str,
    files: Optional[List[str]] = None,
    max_items: int = 5,
) -> str:
    """Build enriched context for a task by pulling relevant data from HexMem.
    
    Returns a context string to prepend to task descriptions, containing:
    - Relevant recent lessons (what we learned doing similar work)
    - Related facts (known information about subjects in the task)
    - Recent related events (what happened recently with these topics)
    """
    context_parts = []
    
    try:
        conn = _connect()
        
        # Extract keywords from description
        keywords = _extract_keywords(description)
        
        # 1. Get relevant lessons
        lessons = _get_relevant_lessons(conn, keywords, task_type, max_items)
        if lessons:
            context_parts.append("## Relevant Lessons\n" + "\n".join(
                f"- [{l['domain']}] {l['lesson']}" + (f" (from: {l['context'][:50]}...)" if l['context'] else "")
                for l in lessons
            ))
        
        # 2. Get related facts about mentioned subjects
        facts = _get_related_facts(conn, keywords, max_items)
        if facts:
            context_parts.append("## Known Facts\n" + "\n".join(
                f"- {f['subject']} {f['predicate']} {f['object']}"
                for f in facts
            ))
        
        # 3. Get recent related events
        events = _get_related_events(conn, keywords, max_items)
        if events:
            context_parts.append("## Recent Context\n" + "\n".join(
                f"- [{e['event_type']}] {e['summary']}"
                for e in events
            ))
        
        # 4. If files mentioned, get any facts about them
        if files:
            file_facts = _get_file_facts(conn, files, max_items)
            if file_facts:
                context_parts.append("## File Notes\n" + "\n".join(
                    f"- {f['file']}: {f['note']}"
                    for f in file_facts
                ))
        
        conn.close()
        
    except Exception as e:
        # Don't fail delegation if context building fails
        context_parts.append(f"(context unavailable: {e})")
    
    if not context_parts:
        return ""
    
    return "---\n### HexMem Context (for reference)\n" + "\n\n".join(context_parts) + "\n---\n\n"


def _extract_keywords(text: str) -> List[str]:
    """Extract meaningful keywords from task description."""
    # Common words to skip
    stopwords = {
        'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
        'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
        'should', 'may', 'might', 'must', 'shall', 'can', 'need', 'dare',
        'ought', 'used', 'to', 'of', 'in', 'for', 'on', 'with', 'at', 'by',
        'from', 'as', 'into', 'through', 'during', 'before', 'after', 'above',
        'below', 'between', 'under', 'again', 'further', 'then', 'once', 'here',
        'there', 'when', 'where', 'why', 'how', 'all', 'each', 'few', 'more',
        'most', 'other', 'some', 'such', 'no', 'nor', 'not', 'only', 'own',
        'same', 'so', 'than', 'too', 'very', 'just', 'and', 'but', 'if', 'or',
        'because', 'until', 'while', 'this', 'that', 'these', 'those', 'what',
        'which', 'who', 'whom', 'it', 'its', 'you', 'your', 'we', 'our', 'i',
        'me', 'my', 'he', 'she', 'they', 'them', 'his', 'her', 'their', 'file',
        'create', 'make', 'write', 'read', 'update', 'add', 'remove', 'please',
    }
    
    words = text.lower().replace('-', ' ').replace('_', ' ').split()
    keywords = []
    for word in words:
        # Clean punctuation
        clean = ''.join(c for c in word if c.isalnum())
        if clean and len(clean) > 2 and clean not in stopwords:
            keywords.append(clean)
    
    # Return unique keywords, preserving order
    seen = set()
    return [k for k in keywords if not (k in seen or seen.add(k))][:10]


def _get_relevant_lessons(
    conn: sqlite3.Connection,
    keywords: List[str],
    task_type: str,
    limit: int,
) -> List[Dict[str, Any]]:
    """Get lessons relevant to the task."""
    results = []
    
    # First try domain match
    domain_map = {
        'code': ['code', 'programming', 'debugging', 'development'],
        'research': ['research', 'investigation', 'analysis'],
        'analysis': ['analysis', 'review', 'assessment'],
        'general': [],
    }
    domains = domain_map.get(task_type, [])
    
    if domains:
        placeholders = ','.join('?' * len(domains))
        rows = conn.execute(
            f"""
            SELECT domain, lesson, context, created_at
            FROM lessons
            WHERE domain IN ({placeholders})
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (*domains, limit),
        ).fetchall()
        for row in rows:
            results.append({
                'domain': row[0],
                'lesson': row[1],
                'context': row[2],
            })
    
    # Also search by keyword
    for keyword in keywords[:3]:
        like = f"%{keyword}%"
        rows = conn.execute(
            """
            SELECT domain, lesson, context, created_at
            FROM lessons
            WHERE lower(lesson) LIKE ? OR lower(context) LIKE ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (like, like, limit),
        ).fetchall()
        for row in rows:
            lesson = {'domain': row[0], 'lesson': row[1], 'context': row[2]}
            if lesson not in results:
                results.append(lesson)
    
    return results[:limit]


def _get_related_facts(
    conn: sqlite3.Connection,
    keywords: List[str],
    limit: int,
) -> List[Dict[str, Any]]:
    """Get facts about subjects mentioned in the task."""
    results = []
    
    for keyword in keywords[:5]:
        like = f"%{keyword}%"
        rows = conn.execute(
            """
            SELECT 
                COALESCE(es.name, f.subject_text) AS subject,
                f.predicate,
                COALESCE(eo.name, f.object_text) AS object
            FROM facts f
            LEFT JOIN entities es ON es.id = f.subject_entity_id
            LEFT JOIN entities eo ON eo.id = f.object_entity_id
            WHERE lower(COALESCE(es.name, f.subject_text, '')) LIKE ?
               OR lower(f.predicate) LIKE ?
               OR lower(COALESCE(eo.name, f.object_text, '')) LIKE ?
            ORDER BY f.created_at DESC
            LIMIT ?
            """,
            (like, like, like, limit),
        ).fetchall()
        for row in rows:
            fact = {'subject': row[0], 'predicate': row[1], 'object': row[2]}
            if fact not in results:
                results.append(fact)
    
    return results[:limit]


def _get_related_events(
    conn: sqlite3.Connection,
    keywords: List[str],
    limit: int,
) -> List[Dict[str, Any]]:
    """Get recent events related to the task."""
    results = []
    
    for keyword in keywords[:3]:
        like = f"%{keyword}%"
        rows = conn.execute(
            """
            SELECT event_type, summary, occurred_at
            FROM events
            WHERE lower(summary) LIKE ? OR lower(details) LIKE ?
            ORDER BY occurred_at DESC
            LIMIT ?
            """,
            (like, like, limit),
        ).fetchall()
        for row in rows:
            event = {'event_type': row[0], 'summary': row[1]}
            if event not in results:
                results.append(event)
    
    return results[:limit]


def _get_file_facts(
    conn: sqlite3.Connection,
    files: List[str],
    limit: int,
) -> List[Dict[str, Any]]:
    """Get any stored facts about specific files."""
    results = []
    
    for file_path in files[:5]:
        filename = Path(file_path).name
        like = f"%{filename}%"
        rows = conn.execute(
            """
            SELECT 
                COALESCE(es.name, f.subject_text) AS subject,
                f.predicate,
                COALESCE(eo.name, f.object_text) AS object
            FROM facts f
            LEFT JOIN entities es ON es.id = f.subject_entity_id
            LEFT JOIN entities eo ON eo.id = f.object_entity_id
            WHERE lower(COALESCE(es.name, f.subject_text, '')) LIKE ?
            LIMIT ?
            """,
            (like, limit),
        ).fetchall()
        for row in rows:
            results.append({
                'file': filename,
                'note': f"{row[1]} {row[2]}",
            })
    
    return results[:limit]


# Agent performance tracking
def record_agent_performance(
    agent_name: str,
    task_type: str,
    success: bool,
    duration_seconds: float,
    tokens_used: int = 0,
) -> Dict[str, Any]:
    """Record agent performance for a task type."""
    try:
        conn = _connect()
        
        # Store as a fact: agent -> completed_successfully/failed_at -> task_type
        predicate = "completed_successfully" if success else "failed_at"
        
        conn.execute(
            """
            INSERT INTO facts (subject_text, predicate, object_text, source)
            VALUES (?, ?, ?, 'hexswarm')
            """,
            (agent_name, predicate, task_type),
        )
        conn.commit()
        conn.close()
        
        return {"recorded": True}
    except Exception as e:
        return {"error": str(e)}


def get_agent_performance(agent_name: str) -> Dict[str, Any]:
    """Get performance stats for an agent."""
    try:
        conn = _connect()
        
        # Count successes and failures by task type
        rows = conn.execute(
            """
            SELECT predicate, object_text, COUNT(*) as count
            FROM facts
            WHERE subject_text = ? AND source = 'hexswarm'
            AND predicate IN ('completed_successfully', 'failed_at')
            GROUP BY predicate, object_text
            """,
            (agent_name,),
        ).fetchall()
        
        conn.close()
        
        stats = {}
        for row in rows:
            task_type = row[1]
            if task_type not in stats:
                stats[task_type] = {'success': 0, 'failure': 0}
            if row[0] == 'completed_successfully':
                stats[task_type]['success'] = row[2]
            else:
                stats[task_type]['failure'] = row[2]
        
        # Calculate success rates
        for task_type in stats:
            total = stats[task_type]['success'] + stats[task_type]['failure']
            stats[task_type]['success_rate'] = (
                stats[task_type]['success'] / total if total > 0 else 0
            )
        
        return {'agent': agent_name, 'stats': stats}
        
    except Exception as e:
        return {'error': str(e)}


def get_best_agent_for_task(task_type: str, available_agents: List[str]) -> Optional[str]:
    """Get the best agent for a task type based on performance history."""
    best_agent = None
    best_rate = -1
    
    try:
        conn = _connect()
        
        for agent in available_agents:
            rows = conn.execute(
                """
                SELECT predicate, COUNT(*) as count
                FROM facts
                WHERE subject_text = ? AND object_text = ? AND source = 'hexswarm'
                AND predicate IN ('completed_successfully', 'failed_at')
                GROUP BY predicate
                """,
                (agent, task_type),
            ).fetchall()
            
            success = 0
            failure = 0
            for row in rows:
                if row[0] == 'completed_successfully':
                    success = row[1]
                else:
                    failure = row[1]
            
            total = success + failure
            if total >= 3:  # Need at least 3 samples
                rate = success / total
                if rate > best_rate:
                    best_rate = rate
                    best_agent = agent
        
        conn.close()
        
    except Exception:
        pass
    
    return best_agent
