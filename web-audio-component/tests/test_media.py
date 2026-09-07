import json
from pathlib import Path
import wave

import pytest

import runner


def short_wave(path):
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8000)
        audio.writeframes(b"\0\0" * 8000 * 20)


@pytest.mark.skipif(not (runner.RUNTIME / "ffmpeg").is_file(), reason="native component tools are not built")
def test_complete_short_audio_without_artwork(tmp_path):
    path = tmp_path / "short.wav"
    short_wave(path)
    result = runner.probe(path)
    assert result["duration_seconds"] == 20
    assert result["codec"] == "pcm_s16le"


def test_metadata_is_audio_free_and_keeps_unavailable_children(monkeypatch, tmp_path):
    def extract(self, url, download):
        assert download is False and self.params["skip_download"] is True
        return {"id": "PL6B3937A5D230E335", "entries": [
            {"id": "f7NwyBnIRTE", "title": "Public"},
            {"id": "YE7VzlLtp-4", "title": "[Private video]"}, None,
        ]}
    monkeypatch.setattr(runner.yt_dlp.YoutubeDL, "extract_info", extract)
    result = runner.operate({"operation": "metadata", "url": "https://www.youtube.com/playlist?list=PL6B3937A5D230E335"})
    assert [entry["available"] for entry in result["entries"]] == [True, False, False]
    assert list(tmp_path.iterdir()) == []


@pytest.mark.skipif(not (runner.RUNTIME / "ffmpeg").is_file(), reason="native component tools are not built")
def test_original_file_preference_identity_and_incomplete_output(monkeypatch, tmp_path):
    info = {"id": "1706333112", "duration": 20, "formats": [{"format_id": "download"}], "ext": "wav"}
    monkeypatch.setattr(runner.yt_dlp.YoutubeDL, "extract_info", lambda *a, **kw: dict(info))
    def process(self, value, download):
        assert download is True and self.params["format"] == "download"
        path = Path(self.params["outtmpl"]["default"].replace("%(ext)s", "wav"))
        short_wave(path)
        return {**value, "requested_downloads": [{"filepath": str(path)}]}
    monkeypatch.setattr(runner.yt_dlp.YoutubeDL, "process_ie_result", process)
    request = {"operation": "download", "url": "https://soundcloud.com/trackistador/kevin-macleod-angevin-b", "item_id": "1706333112", "output_dir": str(tmp_path)}
    with pytest.raises(runner.ComponentError, match="identity_mismatch"):
        runner.operate({**request, "item_id": "999"})
    assert not list(tmp_path.iterdir())
    result = runner.operate(request)
    assert result["processing"] == "native" and result["effective_item_id"] == "1706333112"
    assert result["source_properties"]["bitrate_kbps"] is None
    (tmp_path / result["output_filename"]).unlink()
    info["duration"] = 120
    with pytest.raises(runner.ComponentError, match="incomplete_audio_output"):
        runner.operate(request)


def test_supported_extension_cannot_hide_unsupported_codec(monkeypatch, tmp_path):
    path = tmp_path / "opus.m4a"
    path.write_bytes(b"fixture")
    payload = {"streams": [{"codec_type": "audio", "codec_name": "opus"}], "format": {"duration": 20}}
    monkeypatch.setattr(runner, "run_tool", lambda *a, **kw: json.dumps(payload).encode())
    with pytest.raises(runner.ComponentError, match="unsupported_output_codec"):
        runner.probe(path)


@pytest.mark.parametrize(('url', 'info', 'provider', 'kind', 'item_id'), [
    ('https://music.youtube.com/browse/MPREb_gTAcphH99wE', {'id': 'OLAK5uy_l1m0thk3g31NmIIz_vMIbWtyv7eZixlH0', 'entries': [{'id': 'XNEnEBrHws8', 'title': 'Flat track', 'uploader': 'Do not invent artist'}]}, 'youtube', 'album', 'XNEnEBrHws8'),
    ('https://soundcloud.com/artist/sets/album', {'id': '123', 'entries': [{'id': '456', 'url': 'https://soundcloud.com/artist/song', 'title': 'Album track'}]}, 'soundcloud', 'playlist', '456'),
])
def test_flat_collection_identity_is_preserved_without_fabricated_metadata(monkeypatch, url, info, provider, kind, item_id):
    monkeypatch.setattr(runner.yt_dlp.YoutubeDL, 'extract_info', lambda self, url, download: info)
    result = runner.operate({'operation': 'metadata', 'url': url})
    assert result['provider'] == provider and result['resource_type'] == kind
    assert result['entries'][0]['item_id'] == item_id
    assert result['entries'][0]['available'] is True
    assert result['entries'][0]['artist'] is None and result['entries'][0]['duration_seconds'] is None


@pytest.mark.skipif(not (runner.RUNTIME / 'ffmpeg').is_file(), reason='native component tools are not built')
def test_non_audio_with_supported_extension_is_rejected(tmp_path):
    path = tmp_path / 'not-audio.mp3'
    path.write_text('This is not audio.')
    with pytest.raises(runner.ComponentError, match='media_processing_failed'):
        runner.probe(path)
