"""The pyrekordbox masterPlaylists6.xml orphan warning is filtered out of the
logs (owner feedback 2026-07-08): Rekordbox drops the XML node of deleted
playlists while their DB rows stay soft-deleted, so pyrekordbox re-warns at
every commit, forever, for normal after-gig cleanup."""

import logging

from syncbox.__main__ import _drop_playlist_xml_noise, compose


def _record(msg: str) -> logging.LogRecord:
    return logging.LogRecord(
        "pyrekordbox.db6.database", logging.WARNING, __file__, 0, msg, (), None
    )


def test_drops_the_orphan_playlist_warning():
    assert not _drop_playlist_xml_noise(
        _record(
            "Playlist 111740268 not found in masterPlaylists6.xml! "
            "Did you add it manually? Use the create_playlist method instead."
        )
    )


def test_keeps_every_other_pyrekordbox_warning():
    assert _drop_playlist_xml_noise(_record("No masterPlaylists6.xml found in /x"))
    assert _drop_playlist_xml_noise(_record("anything else"))


def test_compose_registers_the_filter(tmp_path):
    compose(tmp_path)
    assert _drop_playlist_xml_noise in logging.getLogger(
        "pyrekordbox.db6.database"
    ).filters
