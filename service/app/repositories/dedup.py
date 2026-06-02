from __future__ import annotations

from ._mappers import utc_now


class DedupMixin:
    """Persistence for duplicate-detection decisions (mixed into LocalDatabase).

    Stores the canonical keys of duplicate groups the user marked as "not a
    duplicate" so they never resurface on a re-scan.
    """

    def get_dismissed_dedup_keys(self) -> set[str]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT group_key FROM dedup_dismissed"
            ).fetchall()
        return {str(row["group_key"]) for row in rows}

    def add_dismissed_dedup_key(self, group_key: str) -> None:
        if not group_key:
            return
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO dedup_dismissed (group_key, created_at)
                VALUES (?, ?)
                ON CONFLICT(group_key) DO NOTHING
                """,
                (group_key, utc_now()),
            )

    def clear_dismissed_dedup_keys(self) -> int:
        with self.connect() as connection:
            cursor = connection.execute("DELETE FROM dedup_dismissed")
            return cursor.rowcount
