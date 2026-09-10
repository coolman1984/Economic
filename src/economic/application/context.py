"""Application context: wires configuration, database, and repositories."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from ..config import Config, load as load_config
from ..persistence import sqlite_db
from ..persistence.repositories import Repositories


class AppContext:
    """One open database plus the repositories and settings around it."""

    def __init__(self, config: Config, connection):
        self.config = config
        self.connection = connection
        self.repos = Repositories(connection)

    @classmethod
    def open(cls, home: Optional[Path] = None, config_path: Optional[Path] = None,
             overrides: Optional[dict] = None) -> "AppContext":
        config = load_config(home=home, config_path=config_path, overrides=overrides)
        config.ensure_directories()
        connection = sqlite_db.initialize(config.database_path)
        return cls(config, connection)

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "AppContext":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()
