import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import DB_PATH


class SQLiteMemory:
    """Local persistent conversation and long-term memory store.

    This class deliberately keeps persistence dumb and deterministic. It does not
    ask an LLM to decide what is true or what should be saved.
    """

    def __init__(self, path: str | Path = DB_PATH):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        return db

    def _init(self) -> None:
        with self._connect() as db:
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL
                )
                """
            )
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    category TEXT NOT NULL DEFAULT 'general',
                    content TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT 'explicit',
                    importance REAL NOT NULL DEFAULT 0.5,
                    UNIQUE(content)
                )
                """
            )
            db.execute(
                "CREATE INDEX IF NOT EXISTS idx_memories_updated_at ON memories(updated_at DESC)"
            )
            db.execute(
                "CREATE INDEX IF NOT EXISTS idx_memories_category ON memories(category)"
            )

    def add(self, role: str, content: str) -> None:
        timestamp = datetime.now(timezone.utc).isoformat()
        with self._connect() as db:
            db.execute(
                "INSERT INTO events(timestamp, role, content) VALUES (?, ?, ?)",
                (timestamp, role, content),
            )

    def recent(self, limit: int = 20) -> list[tuple[str, str]]:
        limit = max(1, int(limit))
        with self._connect() as db:
            rows = db.execute(
                "SELECT role, content FROM events ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [(row["role"], row["content"]) for row in reversed(rows)]

    def remember(
        self,
        content: str,
        *,
        category: str = "general",
        source: str = "explicit",
        importance: float = 0.5,
    ) -> bool:
        """Persist one explicit user memory.

        Returns True when a new memory was inserted and False when the exact
        normalized content already exists.
        """
        normalized = " ".join(content.split()).strip()
        if not normalized:
            raise ValueError("Memory content cannot be empty.")

        category = category.strip().lower() or "general"
        source = source.strip().lower() or "explicit"
        importance = min(1.0, max(0.0, float(importance)))
        now = datetime.now(timezone.utc).isoformat()

        with self._connect() as db:
            cursor = db.execute(
                """
                INSERT OR IGNORE INTO memories(
                    created_at, updated_at, category, content, source, importance
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (now, now, category, normalized, source, importance),
            )
            inserted = cursor.rowcount == 1
            if not inserted:
                db.execute(
                    """
                    UPDATE memories
                    SET updated_at = ?, category = ?, source = ?, importance = ?
                    WHERE content = ?
                    """,
                    (now, category, source, importance, normalized),
                )
        return inserted

    def list_memories(self, limit: int = 20) -> list[dict]:
        limit = max(1, int(limit))
        with self._connect() as db:
            rows = db.execute(
                """
                SELECT id, created_at, updated_at, category, content, source, importance
                FROM memories
                ORDER BY importance DESC, updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def search_memories(self, query: str, limit: int = 5) -> list[dict]:
        """Search local memories using deterministic token overlap.

        v0.3 intentionally avoids embeddings/vector infrastructure. This is
        enough for a small personal memory store and is easy to inspect.
        """
        tokens = _tokens(query)
        if not tokens:
            return []

        with self._connect() as db:
            rows = db.execute(
                """
                SELECT id, created_at, updated_at, category, content, source, importance
                FROM memories
                ORDER BY updated_at DESC
                """
            ).fetchall()

        scored: list[tuple[float, dict]] = []
        query_lower = query.lower()
        for row in rows:
            item = dict(row)
            content_lower = item["content"].lower()
            content_tokens = _tokens(item["content"])
            overlap = len(tokens & content_tokens)
            if overlap == 0 and query_lower not in content_lower:
                continue

            score = float(overlap)
            if query_lower and query_lower in content_lower:
                score += 2.0
            score += float(item["importance"]) * 0.25
            scored.append((score, item))

        scored.sort(key=lambda pair: (pair[0], pair[1]["updated_at"]), reverse=True)
        return [item for _, item in scored[: max(1, int(limit))]]

    def forget_memory(self, query: str) -> tuple[str, dict | None]:
        """Safely remove one matching memory.

        Returns (status, memory): status is 'deleted', 'none', or 'ambiguous'.
        Ambiguous matches are never deleted automatically.
        """
        matches = self.search_memories(query, limit=2)
        if not matches:
            return "none", None
        if len(matches) > 1:
            return "ambiguous", None

        memory = matches[0]
        with self._connect() as db:
            db.execute("DELETE FROM memories WHERE id = ?", (memory["id"],))
        return "deleted", memory

    def clear_memories(self) -> int:
        with self._connect() as db:
            cursor = db.execute("DELETE FROM memories")
        return cursor.rowcount


def _tokens(text: str) -> set[str]:
    cleaned = "".join(ch.lower() if ch.isalnum() else " " for ch in text)
    return {token for token in cleaned.split() if len(token) >= 3}
