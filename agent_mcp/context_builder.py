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

    Adds a small HexMem-backed cache to avoid re-building similar context bundles.
    """
    context_parts = []

    try:
        conn = _connect()

        # Ensure cache table exists
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS hexswarm_context_cache (
              cache_key TEXT PRIMARY KEY,
              task_type TEXT NOT NULL,
              description_hash TEXT NOT NULL,
              context TEXT NOT NULL,
              created_at TEXT NOT NULL DEFAULT (datetime('now')),
              last_used_at TEXT NOT NULL DEFAULT (datetime('now')),
              use_count INTEGER NOT NULL DEFAULT 0
            );
            """
        )

        # Extract keywords from description
        keywords = _extract_keywords(description)

        # Cache lookup key: task_type + stable keyword set
        import hashlib
        key_material = (task_type + "|" + " ".join(keywords)).encode("utf-8")
        cache_key = hashlib.sha256(key_material).hexdigest()
        desc_hash = hashlib.sha256(description.strip().encode("utf-8")).hexdigest()

        row = conn.execute(
            """
            SELECT context FROM hexswarm_context_cache
            WHERE cache_key = ?
            """,
            (cache_key,),
        ).fetchone()

        if row and row[0]:
            # Update usage counters
            conn.execute(
                """
                UPDATE hexswarm_context_cache
                SET last_used_at = datetime('now'), use_count = use_count + 1
                WHERE cache_key = ?
                """,
                (cache_key,),
            )
            conn.commit()
            return row[0]
        
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
        
        # Finalize
        conn.close()

    except Exception as e:
        # Don't fail delegation if context building fails
        context_parts.append(f"(context unavailable: {e})")

    if not context_parts:
        return ""

    final_context = "---\n### HexMem Context (for reference)\n" + "\n\n".join(context_parts) + "\n---\n\n"

    # Best-effort cache write
    try:
        conn = _connect()
        conn.execute(
            """
            INSERT OR REPLACE INTO hexswarm_context_cache
              (cache_key, task_type, description_hash, context, last_used_at, use_count)
            VALUES
              (?, ?, ?, ?, datetime('now'), COALESCE((SELECT use_count FROM hexswarm_context_cache WHERE cache_key=?),0) + 1)
            """,
            (cache_key, task_type, desc_hash, final_context, cache_key),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass

    return final_context


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


# Agent performance tracking (structured, HexMem-backed)
# NOTE: we keep the old fact-based approach for backwards compatibility by writing
# both a row in hexswarm_agent_performance and a fact.

def _ensure_perf_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS hexswarm_agent_performance (
          id INTEGER PRIMARY KEY,
          ts TEXT NOT NULL DEFAULT (datetime('now')),
          agent_name TEXT NOT NULL,
          task_type TEXT NOT NULL,
          success INTEGER NOT NULL,
          duration_seconds REAL NOT NULL DEFAULT 0,
          tokens_used INTEGER NOT NULL DEFAULT 0,
          source TEXT NOT NULL DEFAULT 'hexswarm'
        );
        """
    )


def record_agent_performance(
    agent_name: str,
    task_type: str,
    success: bool,
    duration_seconds: float,
    tokens_used: int = 0,
) -> Dict[str, Any]:
    """Record a performance sample."""
    try:
        conn = _connect()
        _ensure_perf_tables(conn)

        with conn:
            conn.execute(
                """
                INSERT INTO hexswarm_agent_performance (agent_name, task_type, success, duration_seconds, tokens_used)
                VALUES (?, ?, ?, ?, ?)
                """,
                (agent_name, task_type, 1 if success else 0, float(duration_seconds or 0), int(tokens_used or 0)),
            )

            # Back-compat fact record
            predicate = "completed_successfully" if success else "failed_at"
            conn.execute(
                """
                INSERT INTO facts (subject_text, predicate, object_text, source)
                VALUES (?, ?, ?, 'hexswarm')
                """,
                (agent_name, predicate, task_type),
            )

        conn.close()
        return {"recorded": True}
    except Exception as e:
        return {"error": str(e)}


def get_agent_performance(agent_name: str) -> Dict[str, Any]:
    """Get performance aggregates for an agent (by task type)."""
    try:
        conn = _connect()
        _ensure_perf_tables(conn)

        rows = conn.execute(
            """
            SELECT
              task_type,
              SUM(CASE WHEN success=1 THEN 1 ELSE 0 END) AS success,
              SUM(CASE WHEN success=0 THEN 1 ELSE 0 END) AS failure,
              AVG(duration_seconds) AS avg_duration_seconds,
              AVG(tokens_used) AS avg_tokens_used,
              COUNT(*) AS n
            FROM hexswarm_agent_performance
            WHERE agent_name = ?
            GROUP BY task_type
            """,
            (agent_name,),
        ).fetchall()

        stats: Dict[str, Any] = {}
        for row in rows:
            task_type = row[0]
            success = int(row[1] or 0)
            failure = int(row[2] or 0)
            total = success + failure
            stats[task_type] = {
                "success": success,
                "failure": failure,
                "n": int(row[5] or total),
                "avg_duration_seconds": float(row[3] or 0.0),
                "avg_tokens_used": float(row[4] or 0.0),
                "success_rate": (success / total) if total > 0 else 0.0,
            }

        conn.close()
        return {"agent": agent_name, "stats": stats}

    except Exception as e:
        return {"error": str(e)}


def get_best_agent_for_task(task_type: str, available_agents: List[str]) -> Optional[str]:
    """Pick best agent for a task type.

    Scoring:
      - require >=3 samples
      - prefer higher success_rate
      - tie-breaker: lower avg_duration_seconds

    (We can upgrade to Wilson score later, but this is cheap + robust.)
    """
    best_agent = None
    best_score = None

    try:
        conn = _connect()
        _ensure_perf_tables(conn)

        for agent in available_agents:
            row = conn.execute(
                """
                SELECT
                  SUM(CASE WHEN success=1 THEN 1 ELSE 0 END) AS success,
                  COUNT(*) AS n,
                  AVG(duration_seconds) AS avg_dur
                FROM hexswarm_agent_performance
                WHERE agent_name = ? AND task_type = ?
                """,
                (agent, task_type),
            ).fetchone()
            if not row:
                continue
            success = int(row[0] or 0)
            n = int(row[1] or 0)
            avg_dur = float(row[2] or 0.0)
            if n < 3:
                continue
            rate = success / n if n else 0.0

            # Score tuple: (rate desc, avg_dur asc)
            score = (rate, -avg_dur)
            if best_score is None or score > best_score:
                best_score = score
                best_agent = agent

        conn.close()

    except Exception:
        pass

    return best_agent
