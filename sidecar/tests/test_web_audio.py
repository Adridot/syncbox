"""Base/component installation and protocol boundary with local fixtures."""
import hashlib
import json
from pathlib import Path
import stat
import zipfile

import pytest
from syncbox import web_audio


def archive(tmp_path, monkeypatch, *, protocol=1):
    path = tmp_path / 'fixture.zip'
    check = {'result': 'ok', 'protocol_version': protocol, 'versions': {'yt-dlp': '2026.8.19', 'yt-dlp-ejs': '0.8.0'}, 'ffmpeg': 'ffmpeg version 9.0.1', 'deno': 'deno 2.9.5 (stable, release, aarch64-apple-darwin)'}
    with zipfile.ZipFile(path, 'w') as zipped:
        item = zipfile.ZipInfo(f'{web_audio.NAME}/{web_audio.NAME}')
        item.external_attr = (stat.S_IFREG | 0o755) << 16
        zipped.writestr(item, '#!/bin/sh\ncat >/dev/null\nprintf \'%s\\n\' \'' + json.dumps(check) + "'\n")
    expected = {'component': web_audio.NAME, 'component_version': web_audio.VERSION, 'root': web_audio.NAME, 'executable': web_audio.NAME, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'size': path.stat().st_size, 'versions': check['versions'], 'ffmpeg': check['ffmpeg'], 'deno': check['deno']}
    monkeypatch.setattr(web_audio, 'manifest', lambda: expected)
    monkeypatch.setattr(web_audio.platform, 'system', lambda: 'Darwin')
    monkeypatch.setattr(web_audio.platform, 'machine', lambda: 'arm64')
    monkeypatch.setenv('SYNCBOX_WEB_AUDIO_COMPONENT_ARCHIVE', str(path))
    return path, expected


def test_install_checks_archive_and_protocol_and_preserves_previous_install(tmp_path, monkeypatch):
    path, expected = archive(tmp_path, monkeypatch)
    assert web_audio.install_component(tmp_path)['installed']
    installed = web_audio.component_root(tmp_path) / web_audio.NAME
    original = installed.read_bytes()
    path.write_bytes(b'corrupted')
    with pytest.raises(RuntimeError, match='integrity'):
        web_audio.install_component(tmp_path)
    assert installed.read_bytes() == original
    archive(tmp_path, monkeypatch, protocol=99)
    with pytest.raises(ValueError, match='check_failed'):
        web_audio.install_component(tmp_path)
    assert installed.read_bytes() == original


@pytest.mark.parametrize('filename', ['../outside.wav', '/outside.wav', 'nested/audio.wav', 'audio.exe'])
def test_download_result_requires_a_supported_file_in_its_workspace(tmp_path, monkeypatch, filename):
    monkeypatch.setattr(web_audio, 'component_status', lambda _: {'installed': True})
    monkeypatch.setattr(web_audio, 'invoke', lambda *a, **kw: {'output_filename': filename, 'item_id': '101', 'effective_item_id': '101'})
    with pytest.raises(ValueError, match='invalid_audio_output'):
        web_audio.run(tmp_path, {'operation': 'download', 'output_dir': str(tmp_path), 'item_id': '101'})


def test_download_result_rejects_missing_symlink_and_changed_identity(tmp_path, monkeypatch):
    monkeypatch.setattr(web_audio, 'component_status', lambda _: {'installed': True})
    result = {'output_filename': 'audio.wav', 'item_id': '101', 'effective_item_id': '101'}
    monkeypatch.setattr(web_audio, 'invoke', lambda *a, **kw: result)
    request = {'operation': 'download', 'output_dir': str(tmp_path), 'item_id': '101'}
    with pytest.raises(ValueError, match='invalid_audio_output'):
        web_audio.run(tmp_path, request)
    (tmp_path / 'actual.wav').write_bytes(b'fixture')
    (tmp_path / 'audio.wav').symlink_to(tmp_path / 'actual.wav')
    with pytest.raises(ValueError, match='invalid_audio_output'):
        web_audio.run(tmp_path, request)
    result.update(output_filename='actual.wav', effective_item_id='202')
    with pytest.raises(ValueError, match='source_identity_mismatch'):
        web_audio.run(tmp_path, request)
