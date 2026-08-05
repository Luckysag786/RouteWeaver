from __future__ import annotations

import json
import os
import threading
from pathlib import Path

from .models import AppConfig


APP_DIR_NAME = "RouteWeaver"


def app_data_dir() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    path = base / APP_DIR_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


class ConfigStore:
    def __init__(self, path: Path | None = None):
        self.path = path or app_data_dir() / "config.json"
        self._lock = threading.RLock()

    def load(self) -> AppConfig:
        with self._lock:
            if not self.path.exists():
                return AppConfig()
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                return AppConfig.from_dict(data)
            except (OSError, ValueError, KeyError, TypeError):
                backup = self.path.with_suffix(".invalid.json")
                try:
                    self.path.replace(backup)
                except OSError:
                    pass
                return AppConfig()

    def save(self, config: AppConfig) -> None:
        payload = json.dumps(config.to_dict(), ensure_ascii=False, indent=2)
        temp = self.path.with_suffix(".tmp")
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temp.write_text(payload, encoding="utf-8")
            temp.replace(self.path)

