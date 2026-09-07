"""Inventory and package the isolated web-audio component; never modify the base bundle."""

import argparse
import hashlib
from importlib.metadata import distribution
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tomllib

from reproducible_archive import write_tree_archive
from generate_release_licenses import installed_license, normalized_license, source_from_lock

ROOT = Path(__file__).resolve().parents[1] / "web-audio-component"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--draft", action="store_true", help="Build a local test archive without creating an install manifest")
    args = parser.parse_args()
    licenses = ROOT / "licenses"
    licenses.mkdir(exist_ok=True)
    inventories = [json.loads((licenses / name).read_text()) for name in ("deno-inventory.draft.json", "deno-native/inventory.draft.json")]
    complete = all(value.get("complete") is True for value in inventories)
    if not complete and not args.draft:
        raise SystemExit("Deno runtime/native license inventory is incomplete; use --draft for local tests only")
    for inventory in inventories:
        records = inventory.get("packages", []) if "packages" in inventory else [inventory]
        for record in records:
            if complete and not record.get("files"):
                raise SystemExit(f"missing notices for {record.get('name', 'native runtime')}")
            for item in record.get("files", []):
                path = (licenses / item["path"]).resolve(strict=True)
                if not path.is_relative_to(licenses.resolve()) or hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256"]:
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
    reviewed = ROOT.parent / "release/licenses/optional/texts"
    shutil.copytree(reviewed / "python-runtime", licenses / "python-runtime", dirs_exist_ok=True)
    shutil.copytree(reviewed / "build-runtime/pyinstaller-bootloader-6.21.0",
                    licenses / "pyinstaller-bootloader", dirs_exist_ok=True)
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm",
                    "syncbox-web-audio-component.spec"], cwd=ROOT, check=True)
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    name = project["name"]
    bundle = ROOT / "dist" / name
    archive = ROOT / "dist" / f"{name}-{project['version']}-macos-arm64.zip"
    write_tree_archive(archive, bundle, name)
    result = {"component": name, "version": project["version"], "protocol_version": 1,
              "platform": "macos-arm64", "archive": archive.name, "size": archive.stat().st_size,
              "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(), "license_inventory_complete": complete}
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
