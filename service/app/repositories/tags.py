from __future__ import annotations

import json

from ..models import (
    TagPlaylistMapping,
    TagPlaylistMappingIn,
    TagRule,
    TagRuleIn,
)
from ._mappers import (
    utc_now,
)


class TagsMixin:
    """Tags persistence (mixed into LocalDatabase)."""

    def list_tag_rules(self) -> list[TagRule]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, source_playlist_id, source_playlist_name, tags_json, enabled
                FROM tag_rules
                ORDER BY source_playlist_name COLLATE NOCASE
                """
            ).fetchall()
        return [
            TagRule(
                id=int(row["id"]),
                sourcePlaylistId=str(row["source_playlist_id"]),
                sourcePlaylistName=str(row["source_playlist_name"]),
                tags=json.loads(str(row["tags_json"])),
                enabled=bool(row["enabled"]),
            )
            for row in rows
        ]

    def upsert_tag_rule(self, rule: TagRuleIn) -> TagRule:
        now = utc_now()
        tags_json = json.dumps(rule.tags)
        with self.connect() as connection:
            if rule.id:
                connection.execute(
                    """
                    UPDATE tag_rules
                    SET source_playlist_id = ?,
                        source_playlist_name = ?,
                        tags_json = ?,
                        enabled = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        rule.source_playlist_id,
                        rule.source_playlist_name,
                        tags_json,
                        int(rule.enabled),
                        now,
                        rule.id,
                    ),
                )
                next_id = rule.id
            else:
                cursor = connection.execute(
                    """
                    INSERT INTO tag_rules (
                        source_playlist_id,
                        source_playlist_name,
                        tags_json,
                        enabled,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(source_playlist_id) DO UPDATE SET
                        source_playlist_name = excluded.source_playlist_name,
                        tags_json = excluded.tags_json,
                        enabled = excluded.enabled,
                        updated_at = excluded.updated_at
                    RETURNING id
                    """,
                    (
                        rule.source_playlist_id,
                        rule.source_playlist_name,
                        tags_json,
                        int(rule.enabled),
                        now,
                        now,
                    ),
                )
                next_id = int(cursor.fetchone()["id"])

        return TagRule(id=next_id, **rule.model_dump(by_alias=True, exclude={"id"}))

    def list_tag_playlist_mappings(self) -> list[TagPlaylistMapping]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, tag_name, spotify_playlist_id, spotify_playlist_name, enabled
                FROM tag_playlist_mappings
                ORDER BY tag_name COLLATE NOCASE
                """
            ).fetchall()
        return [
            TagPlaylistMapping(
                id=int(row["id"]),
                tagName=str(row["tag_name"]),
                spotifyPlaylistId=str(row["spotify_playlist_id"]),
                spotifyPlaylistName=str(row["spotify_playlist_name"]),
                enabled=bool(row["enabled"]),
            )
            for row in rows
        ]

    def upsert_tag_playlist_mapping(
        self, mapping: TagPlaylistMappingIn
    ) -> TagPlaylistMapping:
        now = utc_now()
        with self.connect() as connection:
            if mapping.id:
                connection.execute(
                    """
                    UPDATE tag_playlist_mappings
                    SET tag_name = ?,
                        spotify_playlist_id = ?,
                        spotify_playlist_name = ?,
                        enabled = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        mapping.tag_name.strip(),
                        mapping.spotify_playlist_id.strip(),
                        mapping.spotify_playlist_name.strip(),
                        int(mapping.enabled),
                        now,
                        mapping.id,
                    ),
                )
                next_id = mapping.id
            else:
                cursor = connection.execute(
                    """
                    INSERT INTO tag_playlist_mappings (
                        tag_name,
                        spotify_playlist_id,
                        spotify_playlist_name,
                        enabled,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(tag_name) DO UPDATE SET
                        spotify_playlist_id = excluded.spotify_playlist_id,
                        spotify_playlist_name = excluded.spotify_playlist_name,
                        enabled = excluded.enabled,
                        updated_at = excluded.updated_at
                    RETURNING id
                    """,
                    (
                        mapping.tag_name.strip(),
                        mapping.spotify_playlist_id.strip(),
                        mapping.spotify_playlist_name.strip(),
                        int(mapping.enabled),
                        now,
                        now,
                    ),
                )
                next_id = int(cursor.fetchone()["id"])
        return TagPlaylistMapping(
            id=next_id, **mapping.model_dump(by_alias=True, exclude={"id"})
        )
