"""SQLite persistence for entities / screens / transitions."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from plugin.worldmodel.entities.entity import Entity
from plugin.worldmodel.screens.detect import Screen


class WorldStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path))
        self._conn.row_factory = sqlite3.Row
        self._init()

    def _init(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS entities (
              id INTEGER PRIMARY KEY,
              payload TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS screens (
              id INTEGER PRIMARY KEY,
              signature TEXT UNIQUE,
              payload TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS transitions (
              key TEXT PRIMARY KEY,
              payload TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS meta (
              k TEXT PRIMARY KEY,
              v TEXT NOT NULL
            );
            """
        )
        self._conn.commit()

    def save_entities(self, entities: Dict[int, Entity]) -> None:
        self._conn.execute("DELETE FROM entities")
        for e in entities.values():
            self._conn.execute(
                "INSERT INTO entities(id, payload) VALUES (?, ?)",
                (e.id, json.dumps(e.to_dict())),
            )
        self._conn.commit()

    def load_entities(self) -> Dict[int, Entity]:
        rows = self._conn.execute("SELECT id, payload FROM entities").fetchall()
        out: Dict[int, Entity] = {}
        for r in rows:
            e = Entity.from_dict(json.loads(r["payload"]))
            out[e.id] = e
        return out

    def save_screens(self, screens: Dict[str, Screen]) -> None:
        self._conn.execute("DELETE FROM screens")
        for sig, s in screens.items():
            self._conn.execute(
                "INSERT INTO screens(id, signature, payload) VALUES (?, ?, ?)",
                (s.id, sig, json.dumps(s.to_dict())),
            )
        self._conn.commit()

    def set_meta(self, key: str, value: Any) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO meta(k, v) VALUES (?, ?)",
            (key, json.dumps(value)),
        )
        self._conn.commit()

    def get_meta(self, key: str, default: Any = None) -> Any:
        row = self._conn.execute("SELECT v FROM meta WHERE k=?", (key,)).fetchone()
        if not row:
            return default
        return json.loads(row["v"])

    def close(self) -> None:
        self._conn.close()
