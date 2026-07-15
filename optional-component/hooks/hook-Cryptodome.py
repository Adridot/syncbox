"""Collect only the PyCryptodome native modules used by Deezer acquisition."""

from pathlib import Path

from PyInstaller.utils.hooks import collect_dynamic_libs

_REQUIRED_BINARIES = {
    "_cpuid_c",
    "_raw_aes",
    "_raw_blowfish",
    "_raw_cbc",
    "_raw_ecb",
}

binaries = collect_dynamic_libs(
    "Cryptodome",
    search_patterns=[f"{name}.*" for name in sorted(_REQUIRED_BINARIES)],
)
collected = [Path(source).name.split(".", 1)[0] for source, _ in binaries]
if len(collected) != len(_REQUIRED_BINARIES) or set(collected) != _REQUIRED_BINARIES:
    raise RuntimeError(f"unexpected Cryptodome binary set: {sorted(collected)}")

excludedimports = [
    "Cryptodome.Cipher._EKSBlowfish",
    "Cryptodome.Cipher._mode_ccm",
    "Cryptodome.Cipher._mode_cfb",
    "Cryptodome.Cipher._mode_ctr",
    "Cryptodome.Cipher._mode_eax",
    "Cryptodome.Cipher._mode_gcm",
    "Cryptodome.Cipher._mode_kw",
    "Cryptodome.Cipher._mode_kwp",
    "Cryptodome.Cipher._mode_ocb",
    "Cryptodome.Cipher._mode_ofb",
    "Cryptodome.Cipher._mode_openpgp",
    "Cryptodome.Cipher._mode_siv",
    "Cryptodome.Hash",
    "Cryptodome.Protocol",
    "Cryptodome.Util.number",
    "Cryptodome.Util.strxor",
]
