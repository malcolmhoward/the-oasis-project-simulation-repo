"""
Memory / RAG (Retrieval-Augmented Generation) stub — SQLite-backed fact store
with keyword-match retrieval.

No embedding model is loaded.  Retrieval uses simple keyword overlap scoring
rather than vector similarity, enabling deterministic testing of D.A.W.N.'s
context system without a running embedding service.

Example::

    from simulation.layer2.memory_mock import MemoryMock

    mem = MemoryMock()
    fact_id = mem.store("The kitchen lights are Philips Hue bulbs.", metadata={"room": "kitchen"})
    results = mem.retrieve("kitchen lights")
    print(results[0]["text"], results[0]["score"])
"""

from __future__ import annotations

import sqlite3
import uuid
from typing import Any, Dict, List, Optional

from simulation.hal.platform import MemoryInterface


class MemoryMock(MemoryInterface):
    """Keyword-match fact store backed by SQLite.

    Implements :class:`~simulation.hal.platform.MemoryInterface`.

    Uses an in-memory SQLite database by default.  A file path can be
    provided for persistence across sessions.

    Parameters
    ----------
    db_path : str
        SQLite database path.  Use ``":memory:"`` (default) for an
        in-memory database that is discarded when the instance is
        garbage-collected.
    """

    def __init__(self, db_path: str = ":memory:") -> None:
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS facts ("
            "  id TEXT PRIMARY KEY,"
            "  text TEXT NOT NULL,"
            "  metadata TEXT"
            ")"
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    # MemoryInterface implementation
    # ------------------------------------------------------------------

    def store(self, text: str, metadata: Optional[Dict[str, Any]] = None) -> str:
        """Store a fact string.  Returns a unique string identifier."""
        import json
        fact_id = str(uuid.uuid4())
        self._conn.execute(
            "INSERT INTO facts (id, text, metadata) VALUES (?, ?, ?)",
            (fact_id, text, json.dumps(metadata) if metadata else None),
        )
        self._conn.commit()
        return fact_id

    def retrieve(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Retrieve facts by keyword overlap scoring.

        Splits the query into lowercase words and scores each fact by the
        fraction of query words found in the fact text.  Returns up to
        top_k results sorted by descending score.
        """
        import json
        import re
        _strip = re.compile(r"[^\w]")
        query_words = {_strip.sub("", w) for w in query.lower().split()} - {""}
        if not query_words:
            return []

        cursor = self._conn.execute("SELECT id, text, metadata FROM facts")
        scored: list[tuple[float, dict[str, Any]]] = []

        for row in cursor:
            fact_id, text, meta_json = row
            fact_words = {_strip.sub("", w) for w in text.lower().split()} - {""}
            overlap = len(query_words & fact_words)
            if overlap == 0:
                continue
            score = overlap / len(query_words)
            result: dict[str, Any] = {
                "id": fact_id,
                "text": text,
                "score": round(score, 4),
            }
            if meta_json:
                result["metadata"] = json.loads(meta_json)
            scored.append((score, result))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in scored[:top_k]]

    def delete(self, fact_id: str) -> bool:
        """Delete a fact by string identifier.  Returns true if found and deleted."""
        cursor = self._conn.execute("DELETE FROM facts WHERE id = ?", (fact_id,))
        self._conn.commit()
        return cursor.rowcount > 0

    def count(self) -> int:
        """Return the total number of stored facts as an integer."""
        cursor = self._conn.execute("SELECT COUNT(*) FROM facts")
        return cursor.fetchone()[0]

    def close(self) -> None:
        """Close the SQLite connection."""
        self._conn.close()
