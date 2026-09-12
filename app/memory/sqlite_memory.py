import sqlite3
from datetime import datetime, timezone
from app.core.config import DB_PATH

class SQLiteMemory:
    def __init__(self, path=DB_PATH):
        self.path = path
        self._init()
    def _connect(self):
        return sqlite3.connect(self.path)
    def _init(self):
        with self._connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT NOT NULL, role TEXT NOT NULL, content TEXT NOT NULL)")
    def add(self, role: str, content: str):
        timestamp = datetime.now(timezone.utc).isoformat()
        with self._connect() as db:
            db.execute("INSERT INTO events(timestamp, role, content) VALUES (?, ?, ?)", (timestamp, role, content))
    def recent(self, limit: int = 20):
        with self._connect() as db:
            rows = db.execute("SELECT role, content FROM events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return list(reversed(rows))
