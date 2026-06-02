from app import dedup


def _track(cid, title, artist, **kw):
    base = {
        "contentId": str(cid),
        "title": title,
        "artist": artist,
        "durationMs": kw.get("durationMs", 200000),
        "isrc": kw.get("isrc"),
        "filePath": kw.get("filePath", f"/Musique/{cid}.mp3"),
        "fileType": kw.get("fileType", "MP3"),
        "bitRate": kw.get("bitRate", 320),
        "sampleRate": kw.get("sampleRate", 44100),
        "bitDepth": kw.get("bitDepth", 16),
        "fileSize": kw.get("fileSize", 8_000_000),
        "bpm": kw.get("bpm"),
        "rating": kw.get("rating", 0),
        "cueCount": kw.get("cueCount", 0),
        "playlistCount": kw.get("playlistCount", 0),
        "tagCount": kw.get("tagCount", 0),
        "analysed": kw.get("analysed", False),
        "protected": kw.get("protected", False),
        "fileMissing": kw.get("fileMissing", False),
        "dateCreated": kw.get("dateCreated", "2024-01-01"),
    }
    return base


# --- normalisation ---------------------------------------------------------


def test_normalize_title_strips_noise_and_accents():
    assert dedup.normalize_title("Insomnia (Radio Edit)") == "insomnia"
    assert dedup.normalize_title("Cœur (2011 Remaster)") == "coeur"
    assert dedup.normalize_title("Track - Extended Mix") == "track"
    assert dedup.normalize_title("Me & You") == "me and you"


def test_normalize_artist_drops_feat():
    assert dedup.normalize_artist("Calvin Harris feat. Rihanna") == "calvin harris"
    assert dedup.normalize_artist("A & B") == "a and b"


# --- ISRC grouping ---------------------------------------------------------


def test_isrc_groups_high_confidence():
    tracks = [
        _track(1, "Song", "Artist", isrc="USABC1234567"),
        _track(2, "Song (Remaster)", "Artist", isrc="USABC1234567"),
        _track(3, "Other", "Someone", isrc="USXYZ9999999"),
    ]
    groups = dedup.find_duplicate_groups(tracks, strategies=["isrc"], dismissed=set())
    assert len(groups) == 1
    group = groups[0]
    assert group["reason"] == "isrc"
    assert group["confidence"] == 99
    assert {t["contentId"] for t in group["tracks"]} == {"1", "2"}


def test_isrc_with_mismatched_titles_is_flagged():
    # Two genuinely different songs sharing a (wrong) ISRC -> still grouped but
    # downgraded and annotated so the UI warns and bulk-resolve skips it.
    tracks = [
        _track(1, "Get Me High", "Artist A", isrc="USABC1234567"),
        _track(2, "Little Swing", "Artist B", isrc="USABC1234567"),
    ]
    groups = dedup.find_duplicate_groups(tracks, strategies=["isrc"], dismissed=set())
    assert len(groups) == 1
    assert groups[0]["reason"] == "isrc"
    assert groups[0]["confidence"] == 60
    assert groups[0]["note"]


def test_isrc_with_consistent_titles_high_confidence():
    tracks = [
        _track(1, "Thank God", "Rilès", isrc="USABC1234567"),
        _track(2, "THANK GOD", "Rilès", isrc="USABC1234567"),
    ]
    groups = dedup.find_duplicate_groups(tracks, strategies=["isrc"], dismissed=set())
    assert groups[0]["confidence"] == 99
    assert groups[0]["note"] is None


def test_empty_isrc_not_grouped():
    tracks = [
        _track(1, "Song", "Artist", isrc=""),
        _track(2, "Song", "Artist", isrc=None),
    ]
    groups = dedup.find_duplicate_groups(tracks, strategies=["isrc"], dismissed=set())
    assert groups == []


# --- fuzzy grouping --------------------------------------------------------


def test_fuzzy_matches_radio_edit_variant():
    tracks = [
        _track(1, "Insomnia", "Faithless", durationMs=200000),
        _track(2, "Insomnia (Radio Edit)", "Faithless", durationMs=201000),
    ]
    groups = dedup.find_duplicate_groups(
        tracks, strategies=["fuzzy"], fuzzy_threshold=0.85, dismissed=set()
    )
    assert len(groups) == 1
    assert groups[0]["reason"] == "fuzzy"


def test_fuzzy_rejects_different_duration():
    tracks = [
        _track(1, "Insomnia", "Faithless", durationMs=200000),
        _track(2, "Insomnia", "Faithless", durationMs=260000),
    ]
    groups = dedup.find_duplicate_groups(
        tracks, strategies=["fuzzy"], fuzzy_threshold=0.85, dismissed=set()
    )
    assert groups == []


def test_dismissed_group_is_skipped():
    tracks = [
        _track(1, "Song", "Artist", isrc="USABC1234567"),
        _track(2, "Song", "Artist", isrc="USABC1234567"),
    ]
    key = dedup.dismissed_key(["1", "2"])
    groups = dedup.find_duplicate_groups(
        tracks, strategies=["isrc"], dismissed={key}
    )
    assert groups == []


# --- keeper scoring --------------------------------------------------------


def test_keeper_prefers_lossless_over_mp3():
    flac = _track(1, "Song", "Artist", fileType="FLAC", bitRate=1000)
    mp3 = _track(2, "Song", "Artist", fileType="MP3", bitRate=320)
    assert dedup.pick_keeper([mp3, flac]) == "1"


def test_keeper_prefers_protected_permanent_copy():
    event_copy = _track(1, "Song", "Artist", fileType="MP3", cueCount=5)
    permanent = _track(2, "Song", "Artist", fileType="MP3", protected=True)
    assert dedup.pick_keeper([event_copy, permanent]) == "2"


def test_keeper_avoids_missing_file():
    missing = _track(1, "Song", "Artist", fileType="FLAC", fileMissing=True)
    present = _track(2, "Song", "Artist", fileType="MP3", fileMissing=False)
    assert dedup.pick_keeper([missing, present]) == "2"


# --- resolution plan -------------------------------------------------------


def test_plan_never_deletes_protected_file_on_disk():
    tracks = {
        "1": _track(1, "Song", "Artist", protected=True),
        "2": _track(2, "Song", "Artist", protected=False),
    }
    plan = dedup.build_resolution_plan(
        tracks,
        keeper_content_id="2",
        remove_content_ids=["1"],
        allow_file_delete=True,
    )
    assert plan["remove_content_ids"] == ["1"]
    assert plan["files_to_delete"] == []  # protected -> soft-delete only
    assert plan["skipped_protected"] == ["1"]


def test_plan_deletes_unprotected_file_when_allowed():
    tracks = {
        "1": _track(1, "Song", "Artist", protected=False, filePath="/events/x.mp3"),
        "2": _track(2, "Song", "Artist", protected=True),
    }
    plan = dedup.build_resolution_plan(
        tracks,
        keeper_content_id="2",
        remove_content_ids=["1"],
        allow_file_delete=True,
    )
    assert plan["files_to_delete"] == ["/events/x.mp3"]


def test_plan_never_removes_keeper():
    tracks = {"1": _track(1, "Song", "Artist")}
    plan = dedup.build_resolution_plan(
        tracks,
        keeper_content_id="1",
        remove_content_ids=["1"],
        allow_file_delete=True,
    )
    assert plan["remove_content_ids"] == []
