"""Tests for the load-bearing Rekordbox status integers (SPEC-01 1.1).

These integers carry Rekordbox 6/7 sync semantics; if any of them drifts,
the user's Rekordbox sync corrupts. The exact-value tests below MUST fail
on any change to 256/258 or the soft-delete tuple.
"""

from types import SimpleNamespace

from syncbox.safety import statuses


class TestExactIntegers:
    def test_soft_delete_tuple_is_byte_identical(self):
        assert statuses.soft_delete_values() == {
            "rb_local_deleted": 1,
            "rb_local_synced": 0,
            "rb_data_status": 258,
            "rb_local_data_status": 0,
        }

    def test_reactivate_values_are_byte_identical(self):
        assert statuses.reactivate_values() == {
            "rb_data_status": 256,
            "rb_local_deleted": 0,
        }

    def test_status_constants(self):
        assert statuses.RB_DATA_STATUS_ACTIVE == 256
        assert statuses.RB_DATA_STATUS_SOFT_DELETED == 258

    def test_returned_dicts_are_copies(self):
        mutated = statuses.soft_delete_values()
        mutated["rb_data_status"] = 0
        assert statuses.soft_delete_values()["rb_data_status"] == 258
        mutated = statuses.reactivate_values()
        mutated["rb_data_status"] = 0
        assert statuses.reactivate_values()["rb_data_status"] == 256


class TestRoundTrip:
    def test_soft_delete_then_reactivate_on_a_dict(self):
        row = {
            "rb_local_deleted": 0,
            "rb_local_synced": 1,
            "rb_data_status": 256,
            "rb_local_data_status": 3,
        }
        row.update(statuses.soft_delete_values())
        assert row == {
            "rb_local_deleted": 1,
            "rb_local_synced": 0,
            "rb_data_status": 258,
            "rb_local_data_status": 0,
        }
        assert statuses.is_soft_deleted(row)

        row.update(statuses.reactivate_values())
        assert row["rb_data_status"] == 256
        assert row["rb_local_deleted"] == 0
        assert not statuses.is_soft_deleted(row)


class TestIsSoftDeleted:
    def test_mapping_rows(self):
        assert statuses.is_soft_deleted({"rb_local_deleted": 1})
        assert not statuses.is_soft_deleted({"rb_local_deleted": 0})

    def test_attribute_rows(self):
        # Same shape as a pyrekordbox ORM row: plain attribute access.
        assert statuses.is_soft_deleted(SimpleNamespace(rb_local_deleted=1))
        assert not statuses.is_soft_deleted(SimpleNamespace(rb_local_deleted=0))

    def test_missing_field_reads_as_active(self):
        assert not statuses.is_soft_deleted({})
        assert not statuses.is_soft_deleted(SimpleNamespace())
        assert not statuses.is_soft_deleted({"rb_local_deleted": None})

    def test_string_typed_column_values(self):
        # poc/05 caveat 5: some int columns read back through pyrekordbox's
        # VARCHAR mappings; the predicate must not truth-test raw strings.
        assert not statuses.is_soft_deleted({"rb_local_deleted": "0"})
        assert statuses.is_soft_deleted({"rb_local_deleted": "1"})

    def test_filters_a_mixed_list(self):
        rows = [
            {"rb_local_deleted": 0, "id": "a"},
            {"rb_local_deleted": 1, "id": "b"},
            SimpleNamespace(rb_local_deleted=0, id="c"),
            SimpleNamespace(rb_local_deleted=1, id="d"),
        ]
        active = [r for r in rows if not statuses.is_soft_deleted(r)]
        assert [r["id"] if isinstance(r, dict) else r.id for r in active] == ["a", "c"]
