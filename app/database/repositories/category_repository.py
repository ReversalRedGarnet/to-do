"""Data access for the categories table. No business logic here."""

from typing import List


class CategoryRepository:
    def __init__(self, conn):
        self._conn = conn

    def list_all(self) -> List[str]:
        rows = self._conn.execute("SELECT name FROM categories ORDER BY name").fetchall()
        return [r["name"] for r in rows]

    def add(self, name: str) -> None:
        self._conn.execute("INSERT OR IGNORE INTO categories (name) VALUES (?)", (name,))
        self._conn.commit()

    def remove(self, name: str) -> None:
        self._conn.execute("DELETE FROM categories WHERE name = ?", (name,))
        self._conn.commit()
