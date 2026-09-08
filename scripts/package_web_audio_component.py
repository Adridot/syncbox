"""Inventory and package the isolated web-audio component; never modify the base bundle.

Notice texts are not committed: the two inventories pin every text by source and
sha256, and this script materializes them into `licenses/` before packaging.
"""

import argparse
import base64
import hashlib
from importlib.metadata import distribution
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import urllib.request

from reproducible_archive import write_tree_archive
from generate_release_licenses import installed_license, normalized_license, source_from_lock

ROOT = Path(__file__).resolve().parents[1] / "web-audio-component"
INVENTORIES = ("deno-inventory.json", "deno-native/inventory.json")
CACHE = ROOT / "vendor/notice-cache"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def download(url: str, name: str, checksum: str | None = None) -> Path:
    """Cached download under vendor/ (ignored by git); a pinned checksum is enforced."""
    CACHE.mkdir(parents=True, exist_ok=True)
    target = CACHE / name
    if not target.is_file():
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "syncbox-packager"}), timeout=120) as response:
            target.write_bytes(response.read())
    if checksum and sha256(target.read_bytes()) != checksum:
        target.unlink()
        raise SystemExit(f"archive checksum mismatch: {url}")
    return target


_indexes: dict[Path, dict[tuple[str, str], bytes]] = {}


def archive_member(archive: Path, basename: str, checksum: str) -> bytes | None:
    """Find a file in a tarball by name and sha256 (works for .crate and GitHub source archives)."""
    if archive not in _indexes:
        index = {}
        with tarfile.open(archive) as bundle:
            for member in bundle:
                if member.isfile() and member.size <= 4 * 1024 * 1024:
                    data = bundle.extractfile(member).read()
                    index[(Path(member.name).name, sha256(data))] = data
        _indexes[archive] = index
    return _indexes[archive].get((basename, checksum))


def fetch_notice(record: dict, item: dict) -> bytes | None:
    source, basename = item["source"], Path(item["path"]).name
    if source.startswith("release/"):
        return (ROOT.parent / source).read_bytes()
    if source.startswith("https://crates.io/crates/"):
        name, version = record["name"], record["version"]
        crate = download(f"https://static.crates.io/crates/{name}/{name}-{version}.crate",
                         f"{name}-{version}.crate", record.get("crate_checksum"))
        return archive_member(crate, basename, item["sha256"])
    tree = re.fullmatch(r"https://github\.com/([^/]+)/([^/]+)/tree/([^/]+)", source)
    if tree:
        owner, repo, ref = tree.groups()
        tarball = download(f"https://github.com/{owner}/{repo}/archive/{ref}.tar.gz", f"{owner}-{repo}-{ref}.tar.gz")
        return archive_member(tarball, basename, item["sha256"])
    with urllib.request.urlopen(urllib.request.Request(source, headers={"User-Agent": "syncbox-packager"}), timeout=60) as response:
        data = response.read()
    return base64.b64decode(data) if source.endswith("?format=TEXT") else data


def materialize(licenses: Path, inventories: list[dict]) -> None:
    """Every inventoried notice ends up in licenses/ with its pinned sha256; existing matches are kept."""
    for inventory in inventories:
        for record in inventory.get("packages", []) if "packages" in inventory else [inventory]:
            for item in record.get("files", []):
                target = licenses / item["path"]
                if target.is_file() and sha256(target.read_bytes()) == item["sha256"]:
                    continue
                content = fetch_notice(record, item)
                if content is None or sha256(content) != item["sha256"]:
                    raise SystemExit(f"notice unavailable or checksum mismatch: {item['path']} from {item['source']}")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--draft", action="store_true", help="Build a local test archive without creating an install manifest")
    args = parser.parse_args()
    licenses = ROOT / "licenses"
    licenses.mkdir(exist_ok=True)
    inventories = [json.loads((licenses / name).read_text()) for name in INVENTORIES]
    complete = all(value.get("complete") is True for value in inventories)
    if not complete and not args.draft:
        raise SystemExit("Deno runtime/native license inventory is incomplete; use --draft for local tests only")
    materialize(licenses, inventories)
    for inventory in inventories:
        records = inventory.get("packages", []) if "packages" in inventory else [inventory]
        for record in records:
            if complete and not record.get("files"):
                raise SystemExit(f"missing notices for {record.get('name', 'native runtime')}")
            for item in record.get("files", []):
                path = (licenses / item["path"]).resolve(strict=True)
                if not path.is_relative_to(licenses.resolve()) or sha256(path.read_bytes()) != item["sha256"]:
                    raise SystemExit("Deno notice path or checksum mismatch")
    lock = {item["name"]: item for item in tomllib.loads((ROOT / "uv.lock").read_text())["package"]}
    names = ("yt-dlp", "yt-dlp-ejs", "brotli", "certifi", "charset-normalizer",
             "idna", "mutagen", "pycryptodomex", "requests", "urllib3", "websockets")
    entries = []
    for name in names:
        dist = distribution(name)
        files = []
        for file in dist.files or []:
            if any(part.lower().startswith(("license", "copying", "notice")) for part in file.parts):
                source = Path(dist.locate_file(file))
                if source.is_file():
                    target = licenses / name / str(file)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
                    files.append(str(target.relative_to(licenses)))
        if not files:
            raise RuntimeError(f"missing license text for {name}")
        if dist.version != lock[name]["version"]:
            raise SystemExit(f"Python dependency drift: {name}")
        entries.append({"name": name, "version": dist.version,
                        "license": normalized_license(name, installed_license(dist, name), "python"),
                        **source_from_lock(lock[name], ROOT / "uv.lock"),
                        "files": files})
    (licenses / "python-inventory.json").write_text(json.dumps(entries, indent=2) + "\n")
    # python-build-standalone 3.13.11 notices (same runtime lane as the Deezer
    # component) from the reviewed override source, and the PyInstaller
    # bootloader notice from the distribution that froze this component
    runtime = ROOT.parent / "release/license-overrides/python-build-standalone-20260127"
    (licenses / "python-runtime").mkdir(exist_ok=True)
    for notice in ("LICENSE.bzip2.txt", "LICENSE.cpython.txt", "LICENSE.expat.txt", "LICENSE.libffi.txt",
                   "LICENSE.liblzma.txt", "LICENSE.libuuid.txt", "LICENSE.mpdecimal.txt", "LICENSE.openssl-3.txt",
                   "LICENSE.sqlite.txt"):
        shutil.copy2(runtime / notice, licenses / "python-runtime" / notice)
    pyinstaller = distribution("pyinstaller")
    (licenses / "pyinstaller-bootloader").mkdir(exist_ok=True)
    for file in pyinstaller.files or []:
        if file.name.lower().startswith(("license", "copying")):
            shutil.copy2(pyinstaller.locate_file(file), licenses / "pyinstaller-bootloader" / f"{pyinstaller.version}-{file.name}")
    # same determinism knobs as build_macos_release.py: PyInstaller orders
    # base_library.zip from a set, so an unseeded hash randomizes the archive
    # Ignore bytecode cached by earlier test runs as well as preventing writes.
    # Cached ctypes code can have identical semantics but different marshal bytes.
    with tempfile.TemporaryDirectory(prefix="syncbox-web-audio-pycache-") as cache:
        subprocess.run([sys.executable, "-m", "PyInstaller", "--clean", "--noconfirm", "syncbox-web-audio-component.spec"],
                       cwd=ROOT, check=True,
                       env={**os.environ, "PYTHONHASHSEED": "0", "PYTHONDONTWRITEBYTECODE": "1",
                            "PYTHONPYCACHEPREFIX": cache, "TZ": "UTC", "LC_ALL": "C"})
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    name = project["name"]
    bundle = ROOT / "dist" / name
    archive = ROOT / "dist" / f"{name}-{project['version']}-macos-arm64.zip"
    write_tree_archive(archive, bundle, name)
    result = {"component": name, "version": project["version"], "protocol_version": 1,
              "platform": "macos-arm64", "archive": archive.name, "size": archive.stat().st_size,
              "sha256": sha256(archive.read_bytes()), "license_inventory_complete": complete}
    if not args.draft:
        checked = subprocess.run([str(bundle / name)], input='{"operation":"check"}', text=True, capture_output=True, check=True, timeout=40)
        check = json.loads(checked.stdout)
        if check.get("result") != "ok" or check.get("protocol_version") != 1:
            raise SystemExit("frozen web-audio protocol check failed")
        manifest = {**result, "component_version": project["version"], "root": name, "executable": name,
                    "versions": check["versions"], "ffmpeg": check["ffmpeg"], "deno": check["deno"],
                    "download_url": f"https://github.com/Adridot/syncbox/releases/download/v{project['version']}/{archive.name}"}
        target = ROOT.parent / "sidecar/src/syncbox/web_audio_component.json"
        target.write_text(json.dumps(manifest, indent=2) + "\n")
    (ROOT / "dist/build-result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
