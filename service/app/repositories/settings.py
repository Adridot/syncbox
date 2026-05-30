from __future__ import annotations


from ..models import (
    AppSettings,
)


class SettingsMixin:
    """Settings persistence (mixed into LocalDatabase)."""

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
            apiPort=int(self.get_setting("api_port", str(defaults.api_port))),
            permanentPath=self.get_setting("permanent_path", defaults.permanent_path),
            manualCollectionPath=self.get_setting(
                "manual_collection_path", defaults.manual_collection_path
            ),
        )

    def save_app_settings(self, settings: AppSettings) -> AppSettings:
        values = {
            "spotify_client_id": settings.spotify_client_id,
            "spotify_redirect_uri": settings.spotify_redirect_uri,
            "rekordbox_database_dir": settings.rekordbox_database_dir,
            "storage_root": settings.storage_root,
            "api_port": str(settings.api_port),
            "permanent_path": settings.permanent_path,
            "manual_collection_path": settings.manual_collection_path,
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
