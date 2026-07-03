"""Tests for manual relink candidate discovery (SPEC-UNIFIED 5.5, SPEC-01 2.4)."""

from pathlib import Path

from syncbox import relink
from syncbox.relink import CANDIDATE_CAP, find_candidates, iter_audio_files

TRACK = {"title": "Strobe", "artist": "deadmau5", "isrc": "USUS11100310"}


def touch_audio(root: Path, name: str) -> Path:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x00")
    return path


def test_filename_similarity_scores_candidates(tmp_path):
    touch_audio(tmp_path, "deadmau5 - Strobe.mp3")
    touch_audio(tmp_path, "Avicii - Levels.mp3")
    candidates = find_candidates(TRACK, [tmp_path])
    assert len(candidates) == 1
    assert candidates[0]["path"].endswith("deadmau5 - Strobe.mp3")
    assert candidates[0]["score"] >= 70
    assert candidates[0]["format"] == "mp3"


def test_isrc_tag_match_scores_100(tmp_path, monkeypatch):
    target = touch_audio(tmp_path, "unrelated-filename.flac")
    monkeypatch.setattr(
        relink,
        "_file_tags",
        lambda p: ("usus11100310", None) if p == target else (None, None),
    )
    candidates = find_candidates(TRACK, [tmp_path])
    assert candidates[0]["score"] == 100


def test_candidate_cap(tmp_path):
    for i in range(CANDIDATE_CAP + 4):
        touch_audio(tmp_path, f"sub{i}/deadmau5 - Strobe ({i}).mp3")
    candidates = find_candidates(TRACK, [tmp_path])
    assert len(candidates) == CANDIDATE_CAP


def test_walk_is_bounded_f11(tmp_path):
    for i in range(10):
        touch_audio(tmp_path, f"deadmau5 - Strobe take {i}.mp3")
    seen = list(iter_audio_files([tmp_path], max_files=3))
    assert len(seen) <= 3


def test_non_audio_and_missing_roots_are_skipped(tmp_path):
    (tmp_path / "notes.txt").write_text("not audio")
    candidates = find_candidates(TRACK, [tmp_path, tmp_path / "does-not-exist"])
    assert candidates == []


def test_deterministic_ordering(tmp_path):
    touch_audio(tmp_path, "b/deadmau5 - Strobe.mp3")
    touch_audio(tmp_path, "a/deadmau5 - Strobe.mp3")
    first = find_candidates(TRACK, [tmp_path])
    second = find_candidates(TRACK, [tmp_path])
    assert [c["path"] for c in first] == [c["path"] for c in second]
    assert first[0]["path"] < first[1]["path"]  # tie broken by path
