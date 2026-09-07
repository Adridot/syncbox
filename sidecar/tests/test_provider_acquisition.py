"""Exact-source ownership, mixed-provider dispatch and crash recovery."""
import hashlib
import json
from pathlib import Path
import time
import wave

import pytest

from syncbox import acquisition, api, events_service, source_identity, web_audio
from test_acquisition import make_env, seed_event_missing, SECRET_SENTINEL


def direct(env, provider, item_id):
    event = env.conn.execute('SELECT id FROM events LIMIT 1').fetchone()
    row_id = env.conn.execute("INSERT INTO event_tracks (event_id, title, status) VALUES (?, 'Remix', 'missing')", (event['id'],)).lastrowid if event else seed_event_missing(env.conn)
    url = f'https://www.deezer.com/track/{item_id}' if provider == 'deezer' else f'https://www.youtube.com/watch?v={item_id}' if provider == 'youtube' else f'https://soundcloud.com/artist/track-{item_id}'
    env.conn.execute('UPDATE event_tracks SET source_provider = ?, source_item_id = ?, source_url = ?, isrc = NULL WHERE id = ?', (provider, item_id, url, row_id))
    return row_id


@pytest.fixture
def env(tmp_path, monkeypatch):
    value = make_env(tmp_path)
    value.deps.settings.update({'web_audio_enabled': True})
    monkeypatch.setattr(web_audio, 'component_status', lambda _: {'installed': True})
    return value


def output(request, item_id=None):
    path = Path(request['output_dir']) / 'complete.wav'
    with wave.open(str(path), 'wb') as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8000)
        audio.writeframes(b'\0\0' * 8000 * 20)
    return {'output_path': str(path), 'effective_item_id': item_id or request['item_id'], 'processing': 'native', 'source_properties': {'codec': 'pcm_s16le', 'bitrate_kbps': None}, 'output_properties': {'codec': 'pcm_s16le', 'sample_rate': 8000, 'duration_seconds': 20}}


def queue(env, row_id, **extra):
    return env.client.post('/api/acquisition/jobs', json={'scope': 'event', 'row_id': row_id, 'enqueue': True, **extra})


def execute(env, job_id):
    api._update_job(env.conn, job_id, status='running')
    return api._run_acquisition_job(env.deps, job_id)


def test_web_download_needs_no_deezer_or_isrc_and_restores_measured_identity(env):
    row = direct(env, 'youtube', 'f7NwyBnIRTE')
    env.deps.web_audio_runner = lambda _, request, **kw: output(request)
    job = queue(env, row).json()
    assert job['provider'] == 'youtube' and job['event_track_id'] == row
    assert queue(env, row).json()['id'] == job['id']
    result = execute(env, job['id'])
    assert result['status'] == 'downloaded' and result['quality'] is None
    assert result['effective_source_item_id'] == 'f7NwyBnIRTE'
    assert json.loads(result['output_properties'])['duration_seconds'] == 20
    track = dict(env.conn.execute('SELECT * FROM event_tracks WHERE id = ?', (row,)).fetchone())
    assert source_identity.eligible_file(env.conn, track, result['output_path'])
    # The owner update survived, but the process died before marking the job terminal.
    env.conn.execute("UPDATE acquisition_jobs SET status = 'running', phase = 'publishing' WHERE id = ?", (job['id'],))
    env.deps.web_audio_runner = lambda *a, **kw: pytest.fail('published audio must not be downloaded again')
    assert api._run_acquisition_job(env.deps, job['id'])['output_path'] == result['output_path']
    Path(result['output_path']).write_bytes(b'changed audio')
    assert not source_identity.eligible_file(env.conn, track, result['output_path'])


@pytest.mark.parametrize('extra', [{'provider': 'deezer'}, {'deezer_track_id': 101}, {'url': 'https://www.deezer.com/track/101'}, {'source_item_id': 'another'}])
def test_clients_cannot_replace_source_selectors(env, extra):
    row = direct(env, 'soundcloud', '101')
    assert queue(env, row, **extra).status_code == 409
    assert env.conn.execute('SELECT COUNT(*) FROM acquisition_jobs').fetchone()[0] == 0


def test_changed_source_and_removed_owner_cannot_receive_late_audio(env):
    row = direct(env, 'youtube', 'f7NwyBnIRTE')
    job = queue(env, row).json()
    env.conn.execute("UPDATE event_tracks SET source_item_id = 'YE7VzlLtp-4' WHERE id = ?", (row,))
    assert queue(env, row).status_code == 409
    env.deps.web_audio_runner = lambda *a, **kw: pytest.fail('changed selector cannot start downloading')
    assert execute(env, job['id'])['error'] == 'job_source_intent_changed'
    assert env.conn.execute('SELECT status FROM event_tracks WHERE id = ?', (row,)).fetchone()[0] == 'missing'
    job = queue(env, row).json()
    def remove(_, request, *, cancelled):
        env.conn.execute("UPDATE event_tracks SET status = 'removed' WHERE id = ?", (row,))
        assert cancelled()
        return output(request)
    env.deps.web_audio_runner = remove
    assert execute(env, job['id'])['status'] == 'failed'
    assert env.conn.execute('SELECT status FROM event_tracks WHERE id = ?', (row,)).fetchone()[0] == 'removed'
    assert not list(env.storage.rglob('complete.wav'))


def test_effective_id_mismatch_fails_before_publication(env):
    row = direct(env, 'soundcloud', '101')
    env.deps.web_audio_runner = lambda _, request, **kw: output(request, '202')
    result = execute(env, queue(env, row).json()['id'])
    assert result['status'] == 'failed' and result['error'] == 'source_identity_mismatch'
    assert result['published_path'] is None
    assert not list(env.storage.rglob('complete.wav'))


def test_direct_deezer_requires_upgrade_and_strict_mode(env, monkeypatch):
    row = direct(env, 'deezer', '101')
    env.deps.settings.update({'deezer_acquisition_enabled': True})
    env.secrets.set(acquisition.DEEZER_ARL_SECRET, SECRET_SENTINEL)
    monkeypatch.setattr(acquisition, 'component_status', lambda _: {'installed': True, 'capabilities': []})
    assert queue(env, row).json()['message'] == 'deezer_component_upgrade_required'
    monkeypatch.setattr(acquisition, 'component_status', lambda _: {'installed': True, 'capabilities': ['exact_deezer_item']})
    def download(data_dir, arl, isrc, work_dir, **options):
        assert options == {'track_id': 101, 'exact_item': True} and isrc is None
        result = output({'output_dir': str(work_dir), 'item_id': '101'})
        return {**result, 'effective_deezer_track_id': 101}
    env.deps.acquisition_runner = download
    assert execute(env, queue(env, row).json()['id'])['status'] == 'downloaded'


def test_fifo_continues_after_provider_failure_and_retains_owner_correlation(env):
    first = direct(env, 'youtube', 'f7NwyBnIRTE')
    second = direct(env, 'soundcloud', '101')
    calls = []
    def download(_, request, **kw):
        calls.append(request['item_id'])
        if request['item_id'] == 'f7NwyBnIRTE':
            raise ValueError('provider_item_unavailable')
        return output(request)
    env.deps.web_audio_runner = download
    response = env.client.post('/api/acquisition/jobs/batch', json={'items': [{'scope': 'event', 'row_id': first}, {'scope': 'event', 'row_id': second}]})
    assert response.status_code == 202
    assert [job['event_track_id'] for job in response.json()['jobs']] == [first, second]
    worker = api.AcquisitionWorker(env.deps)
    worker.start()
    try:
        deadline = time.monotonic() + 4
        while time.monotonic() < deadline:
            jobs = env.client.get('/api/acquisition/jobs').json()
            if not jobs['active']:
                break
            time.sleep(.02)
        assert not jobs['active']
        assert [job['status'] for job in reversed(jobs['recent'])] == ['failed', 'downloaded']
        assert calls == ['f7NwyBnIRTE', '101']
    finally:
        assert worker.stop()


def test_explicit_local_selection_keeps_source_and_rejects_changed_bytes(env, tmp_path):
    row = direct(env, 'youtube', 'f7NwyBnIRTE')
    audio = output({'output_dir': str(tmp_path), 'item_id': 'fixture'})['output_path']
    response = env.client.post(f'/api/missing/event/{row}/status', json={'status': 'relinked', 'path': audio})
    assert response.status_code == 200, response.text
    track = dict(env.conn.execute('SELECT * FROM event_tracks WHERE id = ?', (row,)).fetchone())
    assert track['source_item_id'] == 'f7NwyBnIRTE' and track['status'] == 'ready'
    assert source_identity.eligible_file(env.conn, track, audio)
    Path(audio).write_bytes(b'changed')
    assert not source_identity.eligible_file(env.conn, track, audio)


def test_spotify_disconnect_preserves_direct_source_jobs_and_previews(env):
    from types import SimpleNamespace
    from syncbox import link_imports
    env.deps.spotify_auth = SimpleNamespace(disconnect=lambda: None)
    row = direct(env, 'youtube', 'f7NwyBnIRTE')
    job = queue(env, row).json()
    event_id = env.conn.execute('SELECT event_id FROM event_tracks WHERE id = ?', (row,)).fetchone()[0]
    preview = link_imports.start(env.conn, event_id, 'https://www.youtube.com/watch?v=f7NwyBnIRTE', 'direct_source_request')
    spotify = link_imports.start(env.conn, event_id, 'https://open.spotify.com/track/' + 'A' * 22, 'spotify_request')
    assert env.client.delete('/api/spotify/session').status_code == 200
    assert api._job_row(env.conn, job['id'])['source_selector'] == job['source_selector']
    assert link_imports.get(env.conn, event_id, preview['id'])['state'] == 'queued'
    assert env.conn.execute('SELECT COUNT(*) FROM event_link_imports WHERE id = ?', (spotify['id'],)).fetchone()[0] == 0
    assert env.conn.execute('SELECT source_item_id FROM event_tracks WHERE id = ?', (row,)).fetchone()[0] == 'f7NwyBnIRTE'
