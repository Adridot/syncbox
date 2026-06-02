import asyncio
from pathlib import Path
from types import SimpleNamespace

from app import collection_acquisition as ca
from app.acquisition import DeezerResolveResult, DeezerTrackCandidate
from app.db import LocalDatabase


def _candidate() -> DeezerTrackCandidate:
    return DeezerTrackCandidate(
        id="42", title="Tenerife Sea", artist="Ed Sheeran",
        album=None, duration_ms=None, payload={},
    )


class FakeResolver:
    async def resolve_by_isrc(self, isrc):
        return DeezerResolveResult(status="resolved", confidence=100, candidate=_candidate())

    async def search(self, query, *, limit=15):
        return [_candidate()]


class FakeClient:
    def __init__(self, queue_items):
        self._queue_items = queue_items
        self.downloaded = []

    async def status(self):
        return SimpleNamespace(available=True, authenticated=True, detail=None)

    async def update_settings(self, settings):
        return {}

    async def download_batch(self, track_ids, name):
        self.downloaded = list(track_ids)
        return {"downloadIds": ["dl-1"]}

    async def queue(self):
        return {"items": self._queue_items}


class FakeAdapter:
    def __init__(self, permanent: Path):
        self._permanent = permanent
        self.relinked = []

    def content_meta(self, content_id):
        return {"contentId": content_id, "title": "Tenerife Sea",
                "artist": "Ed Sheeran", "isrc": "GBAHS1400096"}

    def storage_layout(self):
        return SimpleNamespace(permanent=str(self._permanent))

    def relink_content(self, content_id, file_path):
        self.relinked.append((content_id, file_path))
        return {"contentId": content_id, "filePath": file_path, "backupPath": "/b"}


def _db(tmp_path) -> LocalDatabase:
    db = LocalDatabase(tmp_path / "app.sqlite3")
    db.migrate()
    return db


def test_enqueue_creates_queued_job(tmp_path):
    db = _db(tmp_path)
    adapter = FakeAdapter(tmp_path / "permanent")
    client = FakeClient(queue_items=[])
    result = asyncio.run(
        ca.enqueue_collection_redownload(
            db, adapter, "777", deemix_client=client, deezer_resolver=FakeResolver()
        )
    )
    assert result["status"] == "queued"
    assert client.downloaded == ["42"]
    job = db.get_collection_job("777")
    assert job["status"] == "queued"
    assert job["deezer_track_id"] == "42"
    # And it shows up in the unified global job stream as scope "collection".
    globals_ = db.list_global_acquisition_jobs(scope="collection")
    assert len(globals_) == 1 and globals_[0].track_title == "Tenerife Sea"


def test_sync_relinks_on_download_complete(tmp_path):
    db = _db(tmp_path)
    permanent = tmp_path / "permanent"
    permanent.mkdir()
    # The file Deemix would have written (template "%artist% - %title%").
    (permanent / "Ed Sheeran - Tenerife Sea.mp3").write_bytes(b"x")
    adapter = FakeAdapter(permanent)

    db.upsert_collection_job(
        "777",
        {"status": "queued", "deezer_track_id": "42", "download_id": "dl-1",
         "title": "Tenerife Sea", "artist": "Ed Sheeran", "isrc": "GBAHS1400096",
         "output_dir": str(permanent)},
    )
    client = FakeClient(queue_items=[{"id": "dl-1", "completed": True}])
    asyncio.run(ca.sync_collection_jobs(db, adapter, deemix_client=client))

    assert adapter.relinked == [("777", str(permanent / "Ed Sheeran - Tenerife Sea.mp3"))]
    assert db.get_collection_job("777")["status"] == "ready"


def test_sync_keeps_downloaded_when_relink_fails(tmp_path):
    db = _db(tmp_path)
    permanent = tmp_path / "permanent"
    permanent.mkdir()
    (permanent / "Ed Sheeran - Tenerife Sea.mp3").write_bytes(b"x")

    class FailingAdapter(FakeAdapter):
        def relink_content(self, content_id, file_path):
            raise RuntimeError("Rekordbox is running")

    adapter = FailingAdapter(permanent)
    db.upsert_collection_job(
        "777",
        {"status": "queued", "deezer_track_id": "42", "download_id": "dl-1",
         "title": "Tenerife Sea", "artist": "Ed Sheeran", "isrc": "GBAHS1400096"},
    )
    client = FakeClient(queue_items=[{"id": "dl-1", "completed": True}])
    asyncio.run(ca.sync_collection_jobs(db, adapter, deemix_client=client))

    job = db.get_collection_job("777")
    assert job["status"] == "downloaded"
    assert "Rekordbox is running" in (job["error"] or "")
