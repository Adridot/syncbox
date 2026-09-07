"""Shared eligibility for automatically associating exact linked recordings."""

import hashlib
from pathlib import Path


def exact_source(track):
    return track.get("source_provider") in {"deezer", "youtube", "soundcloud"}


def eligible_file(conn, track, path):
    if not path or Path(path).is_symlink() or not Path(path).is_file():
        return False
    if not exact_source(track):
        return True
    path = Path(path).resolve()
    selected = track.get("selected_local_path")
    if selected and Path(selected).resolve() == path and track.get("selected_local_sha256"):
        try:
            with path.open("rb") as audio:
                return hashlib.file_digest(audio, "sha256").hexdigest() == track["selected_local_sha256"]
        except OSError:
            return False
    for job in conn.execute(
        "SELECT published_path, published_sha256 FROM acquisition_jobs "
        "WHERE provider = ? AND effective_source_item_id = ? AND phase IN ('publishing', 'published')",
        (track["source_provider"], track.get("source_item_id")),
    ):
        if not job["published_path"] or not job["published_sha256"] or Path(job["published_path"]).resolve() != path:
            continue
        try:
            with path.open("rb") as audio:
                if hashlib.file_digest(audio, "sha256").hexdigest() == job["published_sha256"]:
                    return True
        except OSError:
            continue
    return False


def known_file(conn, track):
    for path in (track.get("staging_file_path"), track.get("selected_local_path")):
        if eligible_file(conn, track, path):
            return str(Path(path).resolve())
    for job in conn.execute(
        "SELECT published_path FROM acquisition_jobs WHERE provider = ? AND effective_source_item_id = ? "
        "AND phase IN ('publishing', 'published') ORDER BY id DESC",
        (track["source_provider"], track.get("source_item_id")),
    ):
        if eligible_file(conn, track, job["published_path"]):
            return str(Path(job["published_path"]).resolve())
    return None


def relocate_provenance(conn, source, destination):
    """Carry verified associations across an already verified managed-file move."""
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if not destination.is_file():
        return
    with destination.open("rb") as audio:
        digest = hashlib.file_digest(audio, "sha256").hexdigest()
    conn.execute("SAVEPOINT relocate_source_provenance")
    try:
        identities = set()
        for job in conn.execute("SELECT id, provider, effective_source_item_id, published_path, published_sha256 FROM acquisition_jobs WHERE published_path IS NOT NULL"):
            if Path(job["published_path"]).resolve() == source and job["published_sha256"] == digest:
                conn.execute("UPDATE acquisition_jobs SET published_path = ?, output_path = ? WHERE id = ?", (str(destination), str(destination), job["id"]))
                identities.add((job["provider"], job["effective_source_item_id"]))
        for row in conn.execute("SELECT * FROM event_tracks WHERE source_provider IN ('deezer', 'youtube', 'soundcloud')"):
            track = dict(row)
            selected = track.get("selected_local_path")
            explicit = selected and Path(selected).resolve() == source and track.get("selected_local_sha256") == digest
            if explicit:
                conn.execute("UPDATE event_tracks SET selected_local_path = ? WHERE id = ?", (str(destination), track["id"]))
            staging = track.get("staging_file_path")
            if staging and Path(staging).resolve() == source and (explicit or (track["source_provider"], track["source_item_id"]) in identities):
                conn.execute("UPDATE event_tracks SET staging_file_path = ? WHERE id = ?", (str(destination), track["id"]))
        conn.execute("RELEASE relocate_source_provenance")
    except BaseException:
        conn.execute("ROLLBACK TO relocate_source_provenance")
        conn.execute("RELEASE relocate_source_provenance")
        raise
