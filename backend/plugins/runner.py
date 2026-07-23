from __future__ import annotations

import hashlib
import importlib
import inspect
import threading
from pathlib import Path
from types import ModuleType
from typing import Any

from .reflector import _setup_package_context, reflect_parameters as _reflect_parameters


class PluginRunner:
    def __init__(self):
        self._script_cache: dict[Path, tuple[tuple[int, int], ModuleType]] = {}
        self._cache_lock = threading.RLock()

    def load_callable(
        self,
        *,
        module_path: str | None = None,
        callable_name: str | None = None,
        script_path: str | None = None,
    ):
        if module_path and callable_name:
            module = importlib.import_module(module_path)
            return getattr(module, callable_name)

        if script_path and callable_name:
            module = self._load_script_module(Path(script_path))
            return getattr(module, callable_name)

        raise ValueError("A python module/callable or script/callable pair is required.")

    def run(self, payload: dict[str, Any], context, **entry_config) -> dict[str, Any]:
        callable_obj = self.load_callable(**entry_config)
        if hasattr(callable_obj, "run"):
            return callable_obj.run(payload, context)
        return callable_obj(payload, context)

    def validate_entry(self, **entry_config) -> dict[str, Any]:
        callable_obj = self.load_callable(**entry_config)
        return {
            "ok": True,
            "callable_name": getattr(callable_obj, "__name__", callable_obj.__class__.__name__),
        }

    def reflect_parameters(self, script_path: str) -> dict[str, Any]:
        """读取脚本参数，并确认 run 入口存在。"""
        path = Path(script_path)
        result = _reflect_parameters(path)
        if not result.get("ok"):
            return result

        try:
            callable_obj = self.load_callable(script_path=str(path), callable_name="run")
            inspect.signature(callable_obj).bind({}, object())
            result["callable_name"] = getattr(callable_obj, "__name__", "run")
        except Exception:
            return {"ok": False, "error": "脚本中未找到 run(payload, context) 函数。请确保定义了 def run(payload, context):"}

        return result

    def _load_script_module(self, script_path: Path) -> ModuleType:
        resolved = script_path.resolve()
        stat = resolved.stat()
        fingerprint = (stat.st_mtime_ns, stat.st_size)
        with self._cache_lock:
            cached = self._script_cache.get(resolved)
            if cached is not None and cached[0] == fingerprint:
                return cached[1]

            path_key = hashlib.sha1(str(resolved).encode("utf-8")).hexdigest()[:12]
            module_name = f"isg_plugin_{resolved.stem}_{path_key}"
            spec = importlib.util.spec_from_file_location(module_name, resolved)
            if spec is None or spec.loader is None:
                raise ImportError(f"Unable to load plugin script: {resolved}")
            module = importlib.util.module_from_spec(spec)
            _setup_package_context(module, resolved)
            spec.loader.exec_module(module)
            self._script_cache[resolved] = (fingerprint, module)
            return module
