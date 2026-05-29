from __future__ import annotations

from pathlib import Path
from typing import Any

from .matching import match_spotify_track
from .models import RekordboxTrack, SpotifyTrack


def generate_match_proposals(
    spotify_tracks: list[SpotifyTrack],
    rekordbox_tracks: list[RekordboxTrack],
) -> list[dict[str, Any]]:
    proposals: list[dict[str, Any]] = []
    for spotify_track in spotify_tracks:
        result = match_spotify_track(spotify_track, rekordbox_tracks)
        if result.status == "matched":
            continue
        if result.status == "ambiguous":
            proposals.append(
                {
                    "proposal_type": "manual_match",
                    "spotify_track_id": result.spotify_track_id,
                    "rekordbox_content_id": result.rekordbox_content_id,
                    "reason": result.reason,
                    "payload": {
                        "method": result.method,
                        "confidence": result.confidence,
                    },
                }
            )
        else:
            proposals.append(
                {
                    "proposal_type": "add_to_rekordbox",
                    "spotify_track_id": spotify_track.id,
                    "reason": "Spotify track is missing from Rekordbox.",
                    "payload": spotify_track.model_dump(by_alias=True),
                }
            )
    return proposals


def generate_bidirectional_proposals(
    spotify_track_ids: set[str],
    rekordbox_tracks: list[RekordboxTrack],
    linked_spotify_by_content_id: dict[str, str],
    manual_collection_root: Path,
) -> list[dict[str, Any]]:
    proposals: list[dict[str, Any]] = []
    protected_root = manual_collection_root.expanduser().resolve()

    for track in rekordbox_tracks:
        linked_spotify_id = linked_spotify_by_content_id.get(track.content_id)
        is_manual = is_path_inside(track.file_path, protected_root)

        if is_manual and linked_spotify_id not in spotify_track_ids:
            proposals.append(
                {
                    "proposal_type": "protect_manual_track",
                    "rekordbox_content_id": track.content_id,
                    "file_path": track.file_path,
                    "reason": "Track is in the protected manual collection.",
                    "payload": track.model_dump(by_alias=True),
                }
            )
            continue

        if linked_spotify_id and linked_spotify_id not in spotify_track_ids:
            proposals.append(
                {
                    "proposal_type": "remove_from_rekordbox",
                    "spotify_track_id": linked_spotify_id,
                    "rekordbox_content_id": track.content_id,
                    "file_path": track.file_path,
                    "reason": "Linked Spotify track is no longer present.",
                    "payload": track.model_dump(by_alias=True),
                }
            )

    return proposals


def is_path_inside(path_value: str | None, root: Path) -> bool:
    if not path_value:
        return False
    try:
        Path(path_value).expanduser().resolve().relative_to(root)
        return True
    except ValueError:
        return False
