"""Build the vendored sqlcipher3 binding with Apple CommonCrypto."""

import glob
import os
import sys

from setuptools import Extension, setup


if sys.platform != "darwin":
    raise RuntimeError("syncbox-sqlcipher3-commoncrypto supports macOS only")

os.environ.setdefault("MACOSX_DEPLOYMENT_TARGET", "14.0")

define_macros = [
    ("MODULE_NAME", '"sqlcipher3.dbapi2"'),
    ("SQLITE_ENABLE_FTS3", "1"),
    ("SQLITE_ENABLE_FTS3_PARENTHESIS", "1"),
    ("SQLITE_ENABLE_FTS4", "1"),
    ("SQLITE_ENABLE_FTS5", "1"),
    ("SQLITE_ENABLE_JSON1", "1"),
    ("SQLITE_ENABLE_LOAD_EXTENSION", "1"),
    ("SQLITE_ENABLE_RTREE", "1"),
    ("SQLITE_ENABLE_STAT4", "1"),
    ("SQLITE_ENABLE_UPDATE_DELETE_LIMIT", "1"),
    ("SQLITE_SOUNDEX", "1"),
    ("SQLITE_USE_URI", "1"),
    ("SQLITE_HAS_CODEC", "1"),
    ("SQLITE_TEMP_STORE", "2"),
    ("SQLITE_THREADSAFE", "1"),
    ("SQLITE_EXTRA_INIT", "sqlcipher_extra_init"),
    ("SQLITE_EXTRA_SHUTDOWN", "sqlcipher_extra_shutdown"),
    ("SQLCIPHER_CRYPTO_CC", "1"),
    ("HAVE_STDINT_H", "1"),
    ("SQLITE_MAX_VARIABLE_NUMBER", "250000"),
    ("SQLITE_DEFAULT_PAGE_SIZE", "4096"),
    ("SQLITE_DEFAULT_CACHE_SIZE", "-8000"),
    ("inline", "__inline"),
]

module = Extension(
    name="sqlcipher3._sqlite3",
    sources=glob.glob("src/*.c") + ["vendor/sqlite3.c"],
    define_macros=define_macros,
    include_dirs=["./src"],
    extra_compile_args=[
        "-Qunused-arguments",
        "-g0",
        "-mmacosx-version-min=14.0",
    ],
    extra_link_args=[
        "-mmacosx-version-min=14.0",
        "-Wl,-x",
        "-Wl,-reproducible",
        "-framework",
        "Security",
        "-framework",
        "CoreFoundation",
    ],
    language="c",
)

setup(ext_modules=[module])
