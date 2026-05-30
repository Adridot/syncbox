"""pyrekordbox integration, split by concern.

The former 1323-line ``rekordbox.py`` is now a package:

- ``paths``   — pure path / volume helpers + the ``CollectionPath`` value object
- ``content`` — Rekordbox-DB helpers (MyTags, smart playlists, content, artists)
- ``adapter`` — ``RekordboxAdapter`` + its private read/cache/XML helpers

The public surface is unchanged: ``from app.rekordbox import RekordboxAdapter,
to_volume_relative, ...`` keeps working through these re-exports.
"""

from .paths import *  # noqa: F401,F403
from .content import *  # noqa: F401,F403
from .adapter import *  # noqa: F401,F403

# Private helper consumed by scripts/cleanup_rekordbox.py (star import skips _names).
from .adapter import _remove_playlist_from_xml  # noqa: F401
