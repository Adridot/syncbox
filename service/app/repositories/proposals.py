from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

from ..models import (
    SyncProposal,
)
from ._mappers import (
    proposal_from_row,
    utc_now,
)


class ProposalsMixin:
    """Proposals persistence (mixed into LocalDatabase)."""

    def resolve_proposal(self, proposal_id: int, status: str) -> SyncProposal | None:
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE sync_proposals
                SET status = ?
                WHERE id = ?
                """,
                (status, proposal_id),
            )
        return self.get_proposal(proposal_id)

    def get_proposal(self, proposal_id: int) -> SyncProposal | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT id,
                       proposal_type,
                       status,
                       spotify_track_id,
                       rekordbox_content_id,
                       file_path,
                       reason,
                       payload_json,
                       created_at
                FROM sync_proposals
                WHERE id = ?
                """,
                (proposal_id,),
            ).fetchone()
        return proposal_from_row(row) if row else None

    def insert_proposals(self, proposals: Iterable[dict[str, Any]]) -> int:
        rows = []
        for proposal in proposals:
            rows.append(
                (
                    proposal["proposal_type"],
                    proposal.get("status", "pending"),
                    proposal.get("spotify_track_id"),
                    proposal.get("rekordbox_content_id"),
                    proposal.get("file_path"),
                    proposal["reason"],
                    json.dumps(proposal.get("payload", {})),
                    utc_now(),
                )
            )
        if not rows:
            return 0

        with self.connect() as connection:
            connection.executemany(
                """
                INSERT INTO sync_proposals (
                    proposal_type,
                    status,
                    spotify_track_id,
                    rekordbox_content_id,
                    file_path,
                    reason,
                    payload_json,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
        return len(rows)

    def list_proposals(self) -> list[SyncProposal]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT id,
                       proposal_type,
                       status,
                       spotify_track_id,
                       rekordbox_content_id,
                       file_path,
                       reason,
                       payload_json,
                       created_at
                FROM sync_proposals
                ORDER BY id DESC
                LIMIT 200
                """
            ).fetchall()
        return [
            proposal_from_row(row)
            for row in rows
        ]
