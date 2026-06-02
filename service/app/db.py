"""SQLite gateway for Syncbox app state.

Backwards-compatible facade: the former 1900-line ``LocalDatabase`` God object is
now split by bounded context into ``app/repositories/*`` mixins. ``LocalDatabase``
composes them, so every existing ``database.<method>()`` call site is unchanged.
Row->DTO mappers live in ``app/repositories/_mappers.py`` and are re-exported here
for backwards compatibility.
"""

from __future__ import annotations

from .repositories._base import BaseRepository
from .repositories._mappers import (
    acquisition_job_from_row,
    global_acquisition_job_from_row,
    library_source_from_row,
    library_track_from_row,
    optional_string,
    parse_json_object,
    proposal_from_row,
    utc_now,
)
from .repositories.acquisition import AcquisitionMixin
from .repositories.dedup import DedupMixin
from .repositories.events import EventsMixin
from .repositories.library import LibraryMixin
from .repositories.proposals import ProposalsMixin
from .repositories.settings import SettingsMixin
from .repositories.tags import TagsMixin

__all__ = [
    "LocalDatabase",
    "utc_now",
    "parse_json_object",
    "optional_string",
    "proposal_from_row",
    "library_source_from_row",
    "library_track_from_row",
    "global_acquisition_job_from_row",
    "acquisition_job_from_row",
]


class LocalDatabase(
    SettingsMixin,
    TagsMixin,
    LibraryMixin,
    AcquisitionMixin,
    DedupMixin,
    EventsMixin,
    ProposalsMixin,
    BaseRepository,
):
    """SQLite gateway. Connection + schema live in ``BaseRepository``; the query
    methods are composed from per-context repository mixins (see
    ``app/repositories/``). No behavior change versus the previous monolith."""
