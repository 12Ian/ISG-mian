from __future__ import annotations

import os
from dataclasses import field
from .._compat import slots_dataclass
from pathlib import Path


@slots_dataclass
class BackendPaths:
    root: Path
    data_dir: Path = field(init=False)
    datasets_dir: Path = field(init=False)
    tasks_dir: Path = field(init=False)
    reports_dir: Path = field(init=False)
    models_dir: Path = field(init=False)
    plugins_dir: Path = field(init=False)
    logs_dir: Path = field(init=False)
    settings_dir: Path = field(init=False)
    database_path: Path = field(init=False)

    def __post_init__(self):
        self.root = Path(self.root)
        self.plugins_dir = self.root / "plugins"
        self.logs_dir = self.root / "logs"
        self.settings_dir = self.root / "settings"
        self.models_dir = self._default_user_data_dir() / "models"
        self.set_storage_root("./data")
        self.database_path = self.data_dir / "isg_backend.db"
        for path in [
            self.root,
            self.plugins_dir,
            self.logs_dir,
            self.settings_dir,
            self.models_dir,
        ]:
            path.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _default_user_data_dir() -> Path:
        if os.name == "nt" and os.getenv("LOCALAPPDATA"):
            return Path(os.environ["LOCALAPPDATA"]) / "ISG"
        if os.getenv("XDG_DATA_HOME"):
            return Path(os.environ["XDG_DATA_HOME"]) / "ISG"
        return Path.home() / ".local" / "share" / "ISG"

    def set_storage_root(self, value: str | Path) -> Path:
        storage_root = Path(value).expanduser()
        if not storage_root.is_absolute():
            storage_root = self.root / storage_root
        self.data_dir = storage_root.resolve()
        self.datasets_dir = self.data_dir / "datasets"
        self.tasks_dir = self.data_dir / "tasks"
        self.reports_dir = self.data_dir / "reports"
        for path in [self.data_dir, self.datasets_dir, self.tasks_dir, self.reports_dir]:
            path.mkdir(parents=True, exist_ok=True)
        return self.data_dir
