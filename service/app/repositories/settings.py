from __future__ import annotations


from ..models import (
    AppSettings,
)


class SettingsMixin:
    """Settings persistence (mixed into LocalDatabase)."""

    # Transient OAuth handshake values are never exported/imported.
    _NON_PORTABLE_SETTINGS = {"spotify_oauth_state", "spotify_pkce_verifier"}

    def export_settings(self) -> dict[str, str]:
        """All persisted settings as a flat dict (for portable backup)."""
        with self.connect() as connection:
            rows = connection.execute("SELECT key, value FROM settings").fetchall()
        return {
            str(row["key"]): str(row["value"])
            for row in rows
            if str(row["key"]) not in self._NON_PORTABLE_SETTINGS
        }

    def import_settings(self, values: dict[str, str]) -> int:
        """Upsert a settings dict from a backup. Returns the number applied."""
        applied = [
            (str(key), str(value))
            for key, value in values.items()
            if str(key) not in self._NON_PORTABLE_SETTINGS
        ]
        if not applied:
            return 0
        with self.connect() as connection:
            connection.executemany(
                """
                INSERT INTO settings (key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                applied,
            )
        return len(applied)

    def get_setting(self, key: str, default: str = "") -> str:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT value FROM settings WHERE key = ?",
                (key,),
            ).fetchone()
            return str(row["value"]) if row else default

    def set_setting(self, key: str, value: str) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO settings (key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (key, value),
            )

    def get_app_settings(self, defaults: AppSettings) -> AppSettings:
        return AppSettings(
            spotifyClientId=self.get_setting(
                "spotify_client_id", defaults.spotify_client_id
            ),
            spotifyRedirectUri=self.get_setting(
                "spotify_redirect_uri", defaults.spotify_redirect_uri
            ),
            rekordboxDatabaseDir=self.get_setting(
                "rekordbox_database_dir", defaults.rekordbox_database_dir
            ),
            storageRoot=self.get_setting("storage_root", defaults.storage_root),
            permanentPath=self.get_setting("permanent_path", defaults.permanent_path),
            manualCollectionPath=self.get_setting(
                "manual_collection_path", defaults.manual_collection_path
            ),
            backupRetention=int(
                self.get_setting("backup_retention", str(defaults.backup_retention))
            ),
        )

    def save_app_settings(self, settings: AppSettings) -> AppSettings:
        values = {
            "spotify_client_id": settings.spotify_client_id,
            "spotify_redirect_uri": settings.spotify_redirect_uri,
            "rekordbox_database_dir": settings.rekordbox_database_dir,
            "storage_root": settings.storage_root,
            "permanent_path": settings.permanent_path,
            "manual_collection_path": settings.manual_collection_path,
            "backup_retention": str(settings.backup_retention),
        }
        with self.connect() as connection:
            connection.executemany(
                """
                INSERT INTO settings (key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                values.items(),
            )
        return settings
