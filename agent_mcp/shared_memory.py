"""Shared memory helpers backed by HexMem."""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional


HEXMEM_DB_PATH = Path(os.environ.get("HEXMEM_DB", "~/clawd/hexmem/hexmem.db")).expanduser()


def _connect(db_path: Optional[Path] = None) -> sqlite3.Connection:
    path = db_path or HEXMEM_DB_PATH
    conn = sqlite3.connect(str(path), timeout=5)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def _handle_db_error(error: Exception) -> Dict[str, Any]:
    if isinstance(error, sqlite3.OperationalError) and "database is locked" in str(error).lower():
        return {"error": "database is locked"}
    return {"error": str(error)}


def _canonical(name: str) -> str:
    return "_".join(name.strip().lower().split())


def _get_entity_id(conn: sqlite3.Connection, name: str) -> Optional[int]:
    canonical = _canonical(name)
    row = conn.execute(
        "SELECT id FROM entities WHERE canonical_name = ? LIMIT 1;",
        (canonical,),
    ).fetchone()
    if row:
        return int(row["id"])
    return None


def log_agent_event(
    agent_name: str,
    event_type: str,
    summary: str,
    details: Optional[str] = None,
) -> Dict[str, Any]:
    category = f"agent:{agent_name}"
    try:
        with _connect() as conn:
            with conn:
                cur = conn.execute(
                    """
                    INSERT INTO events (event_type, category, summary, details, significance)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (event_type, category, summary, details or "", 5),
                )
                event_id = cur.lastrowid
                occurred_at = conn.execute(
                    "SELECT occurred_at FROM events WHERE id = ?;", (event_id,)
                ).fetchone()[0]
        return {"event_id": event_id, "occurred_at": occurred_at}
    except Exception as error:
        return _handle_db_error(error)


def share_fact(
    agent_name: str,
    subject: str,
    predicate: str,
    object: str,
) -> Dict[str, Any]:
    source = f"agent:{agent_name}"
    try:
        with _connect() as conn:
            with conn:
                subject_id = _get_entity_id(conn, subject)
                if subject_id is not None:
                    cur = conn.execute(
                        """
                        INSERT INTO facts (subject_entity_id, predicate, object_text, source)
                        VALUES (?, ?, ?, ?)
                        """,
                        (subject_id, predicate, object, source),
                    )
                else:
                    cur = conn.execute(
                        """
                        INSERT INTO facts (subject_text, predicate, object_text, source)
                        VALUES (?, ?, ?, ?)
                        """,
                        (subject, predicate, object, source),
                    )
                fact_id = cur.lastrowid
                created_at = conn.execute(
                    "SELECT created_at FROM facts WHERE id = ?;", (fact_id,)
                ).fetchone()[0]
        return {"fact_id": fact_id, "created_at": created_at}
    except Exception as error:
        return _handle_db_error(error)


def get_shared_context(topic: str, limit: int = 10) -> List[Dict[str, Any]]:
    like = f"%{topic.lower()}%"
    results: List[Dict[str, Any]] = []
    per_table_limit = max(5, limit)

    try:
        with _connect() as conn:
            events = conn.execute(
                """
                SELECT id, occurred_at, event_type, category, summary, details
                FROM events
                WHERE lower(summary) LIKE ?
                   OR lower(details) LIKE ?
                   OR lower(category) LIKE ?
                ORDER BY occurred_at DESC
                LIMIT ?
                """,
                (like, like, like, per_table_limit),
            ).fetchall()
            for row in events:
                results.append(
                    {
                        "type": "event",
                        "id": row["id"],
                        "timestamp": row["occurred_at"],
                        "event_type": row["event_type"],
                        "category": row["category"],
                        "summary": row["summary"],
                        "details": row["details"],
                    }
                )

            facts = conn.execute(
                """
                SELECT f.id,
                       f.created_at,
                       COALESCE(es.name, f.subject_text) AS subject,
                       f.predicate,
                       COALESCE(eo.name, f.object_text) AS object,
                       f.source
                FROM facts f
                LEFT JOIN entities es ON es.id = f.subject_entity_id
                LEFT JOIN entities eo ON eo.id = f.object_entity_id
                WHERE lower(COALESCE(es.name, f.subject_text, '')) LIKE ?
                   OR lower(f.predicate) LIKE ?
                   OR lower(COALESCE(eo.name, f.object_text, '')) LIKE ?
                ORDER BY f.created_at DESC
                LIMIT ?
                """,
                (like, like, like, per_table_limit),
            ).fetchall()
            for row in facts:
                results.append(
                    {
                        "type": "fact",
                        "id": row["id"],
                        "timestamp": row["created_at"],
                        "subject": row["subject"],
                        "predicate": row["predicate"],
                        "object": row["object"],
                        "source": row["source"],
                    }
                )

            interactions = conn.execute(
                """
                SELECT id, occurred_at, channel, counterparty_name, summary
                FROM interactions
                WHERE lower(COALESCE(summary, '')) LIKE ?
                   OR lower(channel) LIKE ?
                   OR lower(COALESCE(counterparty_name, '')) LIKE ?
                ORDER BY occurred_at DESC
                LIMIT ?
                """,
                (like, like, like, per_table_limit),
            ).fetchall()
            for row in interactions:
                results.append(
                    {
                        "type": "interaction",
                        "id": row["id"],
                        "timestamp": row["occurred_at"],
                        "channel": row["channel"],
                        "counterparty": row["counterparty_name"],
                        "summary": row["summary"],
                    }
                )
    except Exception as error:
        return [_handle_db_error(error)]

    results.sort(key=lambda item: item.get("timestamp") or "", reverse=True)
    return results[: max(1, limit)]


def record_handoff(
    from_agent: str,
    to_agent: str,
    task_id: str,
    reason: Optional[str] = None,
) -> Dict[str, Any]:
    summary = f"{from_agent} -> {to_agent} handoff {task_id}"
    details = reason or ""
    metadata = json.dumps(
        {
            "from_agent": from_agent,
            "to_agent": to_agent,
            "task_id": task_id,
            "reason": reason,
        }
    )
    try:
        with _connect() as conn:
            with conn:
                cur = conn.execute(
                    """
                    INSERT INTO events (event_type, category, summary, details, significance, metadata)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    ("handoff", "agent_handoff", summary, details, 6, metadata),
                )
                event_id = cur.lastrowid
                occurred_at = conn.execute(
                    "SELECT occurred_at FROM events WHERE id = ?;", (event_id,)
                ).fetchone()[0]
        return {"event_id": event_id, "occurred_at": occurred_at}
    except Exception as error:
        return _handle_db_error(error)


def share_lesson(
    agent_name: str,
    domain: str,
    lesson: str,
    context: Optional[str] = None,
) -> Dict[str, Any]:
    """Record a lesson learned by an agent."""
    # First log an event, then link the lesson to it
    source_tag = f"agent:{agent_name}"
    try:
        with _connect() as conn:
            with conn:
                # Create a source event for the lesson
                event_cur = conn.execute(
                    """
                    INSERT INTO events (event_type, category, summary, details, significance)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    ("lesson_learned", source_tag, f"Learned: {lesson[:100]}", context or "", 5),
                )
                event_id = event_cur.lastrowid
                
                # Insert the lesson linked to the event
                cur = conn.execute(
                    """
                    INSERT INTO lessons (domain, lesson, context, source_event_id)
                    VALUES (?, ?, ?, ?)
                    """,
                    (domain, lesson, context or "", event_id),
                )
                lesson_id = cur.lastrowid
                created_at = conn.execute(
                    "SELECT created_at FROM lessons WHERE id = ?;", (lesson_id,)
                ).fetchone()[0]
        return {"lesson_id": lesson_id, "created_at": created_at}
    except Exception as error:
        return _handle_db_error(error)


def get_lessons_for_domain(domain: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Get lessons for a specific domain."""
    try:
        with _connect() as conn:
            rows = conn.execute(
                """
                SELECT l.id, l.domain, l.lesson, l.context, l.created_at,
                       e.category as source
                FROM lessons l
                LEFT JOIN events e ON e.id = l.source_event_id
                WHERE lower(l.domain) = lower(?)
                ORDER BY l.created_at DESC
                LIMIT ?
                """,
                (domain, limit),
            ).fetchall()
            return [
                {
                    "id": row["id"],
                    "domain": row["domain"],
                    "lesson": row["lesson"],
                    "context": row["context"],
                    "source": row["source"] or "unknown",
                    "created_at": row["created_at"],
                }
                for row in rows
            ]
    except Exception as error:
        return [_handle_db_error(error)]


def get_agent_lessons(agent_name: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Get lessons learned by a specific agent."""
    source_category = f"agent:{agent_name}"
    try:
        with _connect() as conn:
            rows = conn.execute(
                """
                SELECT l.id, l.domain, l.lesson, l.context, l.created_at
                FROM lessons l
                JOIN events e ON e.id = l.source_event_id
                WHERE e.category = ?
                ORDER BY l.created_at DESC
                LIMIT ?
                """,
                (source_category, limit),
            ).fetchall()
            return [
                {
                    "id": row["id"],
                    "domain": row["domain"],
                    "lesson": row["lesson"],
                    "context": row["context"],
                    "created_at": row["created_at"],
                }
                for row in rows
            ]
    except Exception as error:
        return [_handle_db_error(error)]


def search_lessons(query: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Search lessons by keyword."""
    like = f"%{query.lower()}%"
    try:
        with _connect() as conn:
            rows = conn.execute(
                """
                SELECT l.id, l.domain, l.lesson, l.context, l.created_at,
                       e.category as source
                FROM lessons l
                LEFT JOIN events e ON e.id = l.source_event_id
                WHERE lower(l.lesson) LIKE ? OR lower(l.context) LIKE ? OR lower(l.domain) LIKE ?
                ORDER BY l.created_at DESC
                LIMIT ?
                """,
                (like, like, like, limit),
            ).fetchall()
            return [
                {
                    "id": row["id"],
                    "domain": row["domain"],
                    "lesson": row["lesson"],
                    "context": row["context"],
                    "source": row["source"] or "unknown",
                    "created_at": row["created_at"],
                }
                for row in rows
            ]
    except Exception as error:
        return [_handle_db_error(error)]
