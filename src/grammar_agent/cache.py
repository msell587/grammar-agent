"""A tiny SQLite response cache so re-running on the same text costs nothing."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from pathlib import Path
from types import TracebackType


def cache_key(model_id: str, prompt: str, sentence: str) -> str:
    """SHA-256 of (model, prompt, sentence). Any change to one of them is a miss."""
    blob = json.dumps([model_id, prompt, sentence], ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class ResponseCache:
    """Maps a cache key to the model's raw (already validated) reply text."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        if str(path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(path))
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS responses ("
            " key TEXT PRIMARY KEY, model TEXT NOT NULL, response TEXT NOT NULL,"
            " created_at REAL NOT NULL)"
        )
        self._db.commit()
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> str | None:
        row = self._db.execute("SELECT response FROM responses WHERE key = ?", (key,)).fetchone()
        if row is None:
            self.misses += 1
            return None
        self.hits += 1
        return str(row[0])

    def put(self, key: str, model_id: str, response: str) -> None:
        self._db.execute(
            "INSERT OR REPLACE INTO responses (key, model, response, created_at)"
            " VALUES (?, ?, ?, ?)",
            (key, model_id, response, time.time()),
        )
        self._db.commit()

    def delete(self, key: str) -> None:
        self._db.execute("DELETE FROM responses WHERE key = ?", (key,))
        self._db.commit()

    def __len__(self) -> int:
        return int(self._db.execute("SELECT COUNT(*) FROM responses").fetchone()[0])

    def close(self) -> None:
        self._db.close()

    def __enter__(self) -> ResponseCache:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()
