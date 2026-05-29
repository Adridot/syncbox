from pathlib import Path

from app.models import RekordboxTrack, SpotifyTrack
from app.sync import generate_bidirectional_proposals, generate_match_proposals


def test_manual_collection_track_is_protected_from_deletion() -> None:
    manual_root = Path("/tmp/music/manual_collection")
    proposals = generate_bidirectional_proposals(
        spotify_track_ids=set(),
        rekordbox_tracks=[
            RekordboxTrack(
                contentId="rb1",
                title="Client Upload",
                artist="Client",
                filePath=str(manual_root / "client-upload.mp3"),
                protected=True,
            )
        ],
        linked_spotify_by_content_id={"rb1": "sp1"},
        manual_collection_root=manual_root,
    )

    assert len(proposals) == 1
    assert proposals[0]["proposal_type"] == "protect_manual_track"


def test_missing_spotify_track_generates_rekordbox_add_proposal() -> None:
    proposals = generate_match_proposals(
        spotify_tracks=[
            SpotifyTrack(
                id="sp1",
                uri="spotify:track:sp1",
                title="New Song",
                artists=["Artist"],
                durationMs=200000,
            )
        ],
        rekordbox_tracks=[],
    )

    assert len(proposals) == 1
    assert proposals[0]["proposal_type"] == "add_to_rekordbox"

