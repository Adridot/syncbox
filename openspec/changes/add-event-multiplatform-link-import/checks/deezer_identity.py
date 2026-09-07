"""Exercise the pinned streamrip fallback with a local catalogue fixture only."""

import asyncio
from pathlib import Path
import runpy
import tempfile
from types import SimpleNamespace


def main():
    repo = Path(__file__).resolve().parents[4]
    runner = runpy.run_path(str(repo / "scripts/run_b1_deezer_acquisition.py"))
    with tempfile.TemporaryDirectory(prefix="syncbox-deezer-identity-") as raw:
        component = runner["_load_component"](Path(raw), Path.home())
        import deezer

        calls = []

        def get_track(item_id):
            calls.append(item_id)
            return {
                "FALLBACK": {"SNG_ID": "202"},
                "FILESIZE_MP3_128": "100",
                "FILESIZE_MP3_320": "200",
                "TRACK_TOKEN": item_id,
            }

        def get_url(token, quality):
            if token == "101":
                raise deezer.WrongGeolocation("fixture")
            return "https://media.example.invalid/fixture.mp3"

        client = component["DeezerClient"].__new__(component["DeezerClient"])
        client.config = SimpleNamespace(lower_quality_if_not_available=True)
        client.client = SimpleNamespace(
            gw=SimpleNamespace(get_track=get_track), get_track_url=get_url
        )
        client.session = None
        downloadable = asyncio.run(client.get_downloadable("101", 1))
        assert downloadable.id == "202"
        assert calls == ["101", "202"]
        assert runner["_effective_track_id"](downloadable, 101, False) == 202
        try:
            runner["_effective_track_id"](downloadable, 101, True)
        except runner["PocFailed"] as error:
            assert str(error) == "streamrip_exact_item_unavailable"
        else:
            raise AssertionError("strict mode accepted a fallback")
        print("PASS: requested=101, effective=202; legacy accepted; strict rejected; no network/audio")


if __name__ == "__main__":
    main()
