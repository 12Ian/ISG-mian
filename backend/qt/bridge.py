from __future__ import annotations

import shutil
from pathlib import Path

from .._compat import slots_dataclass

from ..service_facade import BackendServiceFacade
from ..errors import NotFoundError, ValidationError


def _normalize_error(exc: Exception) -> dict:
    if isinstance(exc, NotFoundError):
        return {"ok": False, "error_code": "NOT_FOUND", "message": str(exc)}
    if isinstance(exc, ValidationError):
        return {"ok": False, "error_code": "VALIDATION_ERROR", "message": str(exc)}
    return {"ok": False, "error_code": "INTERNAL_ERROR", "message": str(exc)}


@slots_dataclass
class BackendBridge:
    facade: BackendServiceFacade

    def create_dataset(self, name: str, modality: str, description: str = "") -> dict:
        try:
            return self.facade.dataset_service.create_dataset(
                name,
                self._normalize_modality(modality),
                description,
            )
        except Exception as exc:
            return _normalize_error(exc)

    def update_dataset(self, dataset_id: int, name: str, type_name: str) -> dict:
        try:
            return self.facade.dataset_service.update_dataset(dataset_id, name, type_name)
        except Exception as exc:
            return _normalize_error(exc)

    def delete_dataset(self, dataset_id: int) -> dict:
        try:
            return self.facade.dataset_service.delete_dataset(dataset_id)
        except Exception as exc:
            return _normalize_error(exc)

    def get_datasets(self, page: int, page_size: int, status: str) -> dict:
        try:
            result = self.facade.dataset_service.get_datasets(page, page_size, status)
            result["items"] = [self.to_qml_dataset(item) for item in result.get("items", [])]
            return result
        except Exception as exc:
            return _normalize_error(exc)

    def get_dataset_samples(self, dataset_id: int, page: int, page_size: int, status: str) -> dict:
        try:
            result = self.facade.dataset_service.get_dataset_samples(dataset_id, page, page_size, status)
            result["items"] = [self.to_qml_sample(item) for item in result.get("items", [])]
            return result
        except Exception as exc:
            return _normalize_error(exc)

    def get_dataset_directory(self, dataset_id: int, path: str) -> dict:
        try:
            return self.facade.dataset_service.get_dataset_directory(dataset_id, path)
        except Exception as exc:
            return _normalize_error(exc)

    def get_dataset_preview_samples(self, dataset_id: int, limit: int, status: str) -> dict:
        try:
            result = self.facade.dataset_service.get_dataset_preview_samples(dataset_id, limit, status)
            result["items"] = [self.to_qml_sample(item) for item in result.get("items", [])]
            return result
        except Exception as exc:
            return _normalize_error(exc)

    def get_sample_preview(self, sample_id: int) -> dict:
        try:
            result = self.facade.dataset_service.get_sample_preview(sample_id)
            if result.get("ok") and "data" in result:
                result["data"] = self.to_qml_sample(result["data"])
            return result
        except Exception as exc:
            return _normalize_error(exc)

    def get_dataset_stats(self, dataset_id: int) -> dict:
        try:
            return self.facade.dataset_service.get_dataset_stats(dataset_id)
        except Exception as exc:
            return _normalize_error(exc)

    def import_files(self, dataset_id: int, file_paths: list[str]) -> dict:
        try:
            return self.facade.dataset_service.import_files(dataset_id, file_paths)
        except Exception as exc:
            return _normalize_error(exc)

    def import_folder(self, dataset_id: int, folder_path: str, include_subfolders: bool) -> dict:
        try:
            return self.facade.dataset_service.import_folder(dataset_id, folder_path, include_subfolders)
        except Exception as exc:
            return _normalize_error(exc)

    def import_dataset_bundle(self, payload: dict) -> dict:
        try:
            result = self.facade.dataset_service.import_dataset_bundle(payload or {})
            if result.get("ok"):
                result["data"]["datasets"] = [self.to_qml_dataset(item) for item in result["data"].get("datasets", [])]
                if result["data"].get("train_dataset"):
                    result["data"]["train_dataset"] = self.to_qml_dataset(result["data"]["train_dataset"])
                if result["data"].get("test_dataset"):
                    result["data"]["test_dataset"] = self.to_qml_dataset(result["data"]["test_dataset"])
            return result
        except Exception as exc:
            return _normalize_error(exc)


    def get_system_stats(self) -> dict:
        try:
            return self.facade.dataset_service.get_system_stats()
        except Exception as exc:
            return _normalize_error(exc)

    def get_recent_activities(self, limit: int = 5) -> list[dict]:
        try:
            return self.facade.dataset_service.get_recent_activities(limit)
        except Exception:
            return []  # type: ignore[return-value]

    def get_data_type_distribution(self) -> dict:
        try:
            return self.facade.dataset_service.get_data_type_distribution()
        except Exception as exc:
            return _normalize_error(exc)


    def get_algorithms(self, category: str, modality: str) -> list[dict]:
        try:
            normalized_modality = self._normalize_modality(modality) if (modality or "").strip() else ""
            return self.facade.algorithm_service.get_algorithms(category, normalized_modality)
        except Exception:
            return []  # type: ignore[return-value]

    def create_algorithm(self, payload: dict) -> dict:
        try:
            return self.facade.algorithm_service.create_algorithm(payload)
        except Exception as exc:
            return _normalize_error(exc)

    def update_algorithm(self, algorithm_id: int, payload: dict) -> dict:
        try:
            return self.facade.algorithm_service.update_algorithm(algorithm_id, payload)
        except Exception as exc:
            return _normalize_error(exc)

    def delete_algorithm(self, algorithm_id: int) -> dict:
        try:
            return self.facade.algorithm_service.delete_algorithm(algorithm_id)
        except Exception as exc:
            return _normalize_error(exc)

    def set_algorithm_enabled(self, algorithm_id: int, enabled: bool) -> dict:
        try:
            return self.facade.algorithm_service.set_algorithm_enabled(algorithm_id, enabled)
        except Exception as exc:
            return _normalize_error(exc)

    def validate_algorithm(self, algorithm_id: int) -> dict:
        try:
            return self.facade.algorithm_service.validate_algorithm(algorithm_id)
        except Exception as exc:
            return _normalize_error(exc)

    def get_tasks(self, task_type: str, status: str, page: int, page_size: int) -> dict:
        try:
            result = self.facade.task_repository.list_tasks(
                task_type=task_type or "",
                status=status or "",
                page=max(page, 1),
                page_size=max(page_size, 1),
            )
            result["items"] = [self._serialize_task(item) for item in result.get("items", [])]
            return result
        except Exception as exc:
            return _normalize_error(exc)

    def start_task(self, task_id: int) -> dict:
        try:
            return self.facade.task_manager.start(task_id)
        except Exception as exc:
            return _normalize_error(exc)

    def delete_task(self, task_id: int) -> dict:
        try:
            with self.facade.session_factory() as session:
                result = self.facade.task_repository.delete_task(session, task_id)
                if result is None:
                    return {"ok": False, "error_code": "NOT_FOUND", "message": f"Task {task_id} not found."}
                session.commit()
                return {"ok": True, "data": result}
        except Exception as exc:
            return _normalize_error(exc)

    def cancel_task(self, task_id: int) -> dict:
        try:
            return self.facade.task_manager.cancel(task_id)
        except Exception as exc:
            return _normalize_error(exc)

    def get_task_logs(self, task_id: int, page: int, page_size: int) -> dict:
        try:
            result = self.facade.task_repository.list_task_logs(
                task_id, page=max(page, 1), page_size=max(page_size, 1)
            )
            result["items"] = [self._serialize_task_log(item) for item in result.get("items", [])]
            return result
        except Exception as exc:
            return _normalize_error(exc)

    def create_cleaning_task(self, dataset_id: int, algorithm_ids: list[int], parameters: dict) -> dict:
        try:
            return self.facade.cleaning_service.create_task(dataset_id, algorithm_ids, parameters)
        except Exception as exc:
            return _normalize_error(exc)

    def get_cleaning_tasks(self, dataset_id: int, status: str, page: int = 1, page_size: int = 100) -> dict:
        try:
            return self.get_tasks("cleaning", status, page, page_size)
        except Exception as exc:
            return _normalize_error(exc)

    def get_cleaning_suggestions(self, task_id: int, status: str, page: int, page_size: int) -> dict:
        try:
            return self.facade.cleaning_service.list_suggestions(task_id, status or None, page, page_size)
        except Exception as exc:
            return _normalize_error(exc)

    def approve_cleaning_suggestion(self, suggestion_id: int, action: str) -> dict:
        try:
            return self.facade.cleaning_service.handle_suggestion(suggestion_id, action)
        except Exception as exc:
            return _normalize_error(exc)

    def batch_approve_cleaning_suggestions(self, suggestion_ids: list[int], action: str) -> dict:
        try:
            return self.facade.cleaning_service.batch_handle_suggestions(suggestion_ids, action)
        except Exception as exc:
            return _normalize_error(exc)

    def store_cleaning_task_result(self, task_id: int, dataset_name: str) -> dict:
        try:
            return self.facade.cleaning_service.store_cleaned_dataset(task_id, dataset_name)
        except Exception as exc:
            return _normalize_error(exc)

    def run_cleaning_task(self, task_id: int) -> dict:
        try:
            self.facade.task_manager.start(task_id)
            return self.facade.cleaning_service.run_task(task_id)
        except Exception as exc:
            return _normalize_error(exc)

    def create_generation_task(
        self,
        source_dataset_id: int,
        target_dataset_id: int,
        algorithm_ids: list[int],
        parameters: dict,
        target_count: int,
    ) -> dict:
        try:
            return self.facade.generation_service.create_task(
                source_dataset_id, target_dataset_id, algorithm_ids, parameters, target_count
            )
        except Exception as exc:
            return _normalize_error(exc)

    def get_generation_tasks(self, dataset_id: int, status: str) -> dict:
        try:
            return self.get_tasks("generation", status, 1, 200)
        except Exception as exc:
            return _normalize_error(exc)

    def get_generation_outputs(self, task_id: int, status: str, page: int, page_size: int) -> dict:
        try:
            return self.facade.generation_service.list_outputs(task_id, status or None, page, page_size)
        except Exception as exc:
            return _normalize_error(exc)

    def run_generation_task(self, task_id: int) -> dict:
        try:
            self.facade.task_manager.start(task_id)
            return self.facade.generation_service.run_task(task_id)
        except Exception as exc:
            return _normalize_error(exc)

    def create_training_task(
        self,
        scenario_id: int,
        dataset_id: int,
        algorithm_id: int,
        parameters: dict,
    ) -> dict:
        try:
            return self.facade.training_service.create_task(
                scenario_id, dataset_id, algorithm_id, parameters
            )
        except Exception as exc:
            return _normalize_error(exc)

    def get_training_tasks(self, dataset_id: int, status: str) -> dict:
        try:
            return self.get_tasks("training", status, 1, 200)
        except Exception as exc:
            return _normalize_error(exc)

    def run_training_task(self, task_id: int) -> dict:
        try:
            self.facade.task_manager.start(task_id)
            return self.facade.training_service.run_task(task_id)
        except Exception as exc:
            return _normalize_error(exc)

    def import_test_set(self, dataset_name: str, folder_path: str) -> dict:
        try:
            return self.facade.dataset_service.import_folder_with_stage(
                dataset_name, folder_path, stage="test"
            )
        except Exception as exc:
            return _normalize_error(exc)

    def get_scenarios(self, modality: str = "") -> list[dict]:
        try:
            return self.facade.evaluation_service.list_scenarios(modality or None)
        except Exception:
            return []  # type: ignore[return-value]

    def create_evaluation_task(
        self,
        scenario_id: int,
        baseline_dataset_id: int,
        target_dataset_id: int,
        algorithm_id: int,
        parameters: dict,
    ) -> dict:
        try:
            return self.facade.evaluation_service.create_task(
                scenario_id, baseline_dataset_id, target_dataset_id, algorithm_id, parameters
            )
        except Exception as exc:
            return _normalize_error(exc)

    def get_evaluation_tasks(self, status: str) -> dict:
        try:
            return self.get_tasks("evaluation", status, 1, 200)
        except Exception as exc:
            return _normalize_error(exc)

    def get_evaluation_results(self, task_id: int) -> dict:
        try:
            return self.facade.evaluation_service.get_results(task_id)
        except Exception as exc:
            return _normalize_error(exc)

    def export_evaluation_report(self, task_id: int, output_path: str) -> dict:
        try:
            return self.facade.evaluation_service.export_report(task_id, output_path)
        except Exception as exc:
            return _normalize_error(exc)

    def run_evaluation_task(self, task_id: int) -> dict:
        try:
            self.facade.task_manager.start(task_id)
            return self.facade.evaluation_service.run_task(task_id)
        except Exception as exc:
            return _normalize_error(exc)

    def get_system_status(self) -> dict:
        try:
            return self.facade.settings_service.get_system_status()
        except Exception as exc:
            return _normalize_error(exc)

    def get_settings(self) -> dict:
        try:
            return self.facade.settings_service.get_settings()
        except Exception as exc:
            return _normalize_error(exc)

    def update_setting(self, key: str, value) -> dict:
        try:
            return self.facade.settings_service.update_setting(key, value)
        except Exception as exc:
            return _normalize_error(exc)

    def ensure_default_settings(self) -> None:
        self.facade.settings_service.ensure_defaults()

    def seed_default_algorithms(self) -> None:
        from ..seed_data import DEFAULT_ALGORITHMS
        existing = self.facade.algorithm_service.get_algorithms("", "")
        existing_keys = {a["key"] for a in existing}
        for algo in DEFAULT_ALGORITHMS:
            if algo["key"] not in existing_keys:
                self.facade.algorithm_service.create_algorithm(dict(algo))

    def reflect_parameters(self, script_path: str) -> dict:
        """从 .py 脚本反射参数列表。"""
        try:
            return self.facade.algorithm_service.plugin_runner.reflect_parameters(script_path)
        except Exception as exc:
            return _normalize_error(exc)

    def import_plugin_file(self, source_path: str) -> dict:
        """将用户上传的 .py 文件复制到 plugins/user/ 目录。"""
        try:
            src = Path(source_path).resolve()
            if not src.exists():
                return {"ok": False, "error_code": "NOT_FOUND", "message": f"源文件不存在: {src}"}
            plugins_user_dir = self.facade.paths.plugins_dir / "user"
            plugins_user_dir.mkdir(parents=True, exist_ok=True)
            dest = plugins_user_dir / src.name
            if src == dest.resolve():
                return {"ok": True, "path": str(dest)}
            if dest.exists():
                dest.unlink()
            shutil.copy2(src, dest)
            return {"ok": True, "path": str(dest)}
        except Exception as exc:
            return _normalize_error(exc)

    def get_operation_logs(self, page: int, page_size: int, resource_type: str = "") -> dict:
        try:
            return self.facade.settings_service.list_operation_logs(page, page_size, resource_type)
        except Exception as exc:
            return _normalize_error(exc)


    def _normalize_modality(self, modality: str) -> str:
        return {
            "\u56fe\u50cf": "image",
            "\u6587\u672c": "text",
            "\u97f3\u9891": "audio",
            "\u8868\u683c": "tabular",
            "\u89c6\u9891": "video",
            "\u591a\u6a21\u6001": "multimodal",
            "\u5176\u4ed6": "other",
        }.get((modality or "").strip(), (modality or "").strip() or "other")

    def to_qml_dataset(self, item: dict) -> dict:
        size_bytes = int(item.get("size_bytes") or 0)
        stage = self._dataset_stage(item)
        return {
            **item,
            "type": self._qml_modality_label(item.get("modality", "")),
            "sampleCount": item.get("total_samples", 0),
            "size": self._format_size(size_bytes),
            "stage": stage,
            "stageLabel": self._dataset_stage_label(stage),
        }

    def to_qml_sample(self, item: dict) -> dict:
        size_bytes = int(item.get("size_bytes") or 0)
        return {
            **item,
            "type": self._qml_modality_label(item.get("modality", "")),
            "size": self._format_size(size_bytes),
            "modified": item.get("updated_at", ""),
        }

    def _qml_modality_label(self, modality: str) -> str:
        return {
            "image": "\u56fe\u50cf",
            "text": "\u6587\u672c",
            "audio": "\u97f3\u9891",
            "tabular": "\u8868\u683c",
            "video": "\u89c6\u9891",
            "multimodal": "\u591a\u6a21\u6001",
        }.get(modality, modality or "\u5176\u4ed6")

    def _dataset_stage(self, item: dict) -> str:
        status = str(item.get("status", "")).lower()
        tags = {str(tag).lower() for tag in (item.get("tags") or [])}
        if status == "deleted" or "deleted" in tags:
            return "deleted"
        if status == "cleaned" or "cleaned" in tags:
            return "cleaned"
        if status == "generated" or "generated" in tags:
            return "generated"
        if status in {"imported", "created", "raw", "test"} or "imported" in tags or "raw" in tags or "test" in tags:
            return "raw"
        return status or "raw"

    def _dataset_stage_label(self, stage: str) -> str:
        return {
            "raw": "\u539f\u59cb\u6570\u636e\u96c6",
            "cleaned": "\u6e05\u6d17\u6570\u636e\u96c6",
            "generated": "\u751f\u6210\u6570\u636e\u96c6",
            "deleted": "\u5df2\u5220\u9664",
        }.get(stage, "\u539f\u59cb\u6570\u636e\u96c6")

    def _format_size(self, size_bytes: int) -> str:
        if size_bytes >= 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"
        if size_bytes >= 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
        if size_bytes >= 1024:
            return f"{size_bytes / 1024:.1f} KB"
        return f"{size_bytes} B"

    def _serialize_task(self, task) -> dict:
        if isinstance(task, dict):
            return {
                "id": task.get("id"),
                "task_type": task.get("task_type", ""),
                "status": task.get("status", ""),
                "title": task.get("title") or "",
                "progress": task.get("progress", 0.0),
                "progress_message": task.get("progress_message") or "",
                "source_dataset_id": task.get("source_dataset_id"),
                "target_dataset_id": task.get("target_dataset_id"),
                "source_dataset_name": task.get("source_dataset_name") or "",
                "source_dataset_path": task.get("source_dataset_path") or "",
                "target_dataset_name": task.get("target_dataset_name") or "",
                "target_dataset_path": task.get("target_dataset_path") or "",
                "algorithm_id": task.get("algorithm_id"),
                "error_message": task.get("error_message") or "",
                "output_dir": task.get("output_dir") or "",
                "parameters": task.get("parameters_json") or task.get("parameters") or {},
                "payload": task.get("payload_json") or task.get("payload") or {},
                "result": task.get("result_json") or task.get("result") or {},
                "created_at": task.get("created_at") or "",
            }
        return {
            "id": task.id,
            "task_type": task.task_type,
            "status": task.status,
            "progress": task.progress,
            "progress_message": task.progress_message or "",
            "source_dataset_id": task.source_dataset_id,
            "target_dataset_id": task.target_dataset_id,
            "algorithm_id": task.algorithm_id,
            "error_message": task.error_message or "",
            "parameters": task.parameters_json or {},
            "payload": task.payload_json or {},
            "result": task.result_json or {},
            "created_at": task.created_at.isoformat() if task.created_at else "",
        }

    def _serialize_task_log(self, item) -> dict:
        if isinstance(item, dict):
            return {
                "id": item.get("id"),
                "task_id": item.get("task_id"),
                "level": item.get("level", ""),
                "message": item.get("message", ""),
                "payload": item.get("payload_json") or item.get("payload") or {},
                "created_at": item.get("created_at") or "",
            }
        return {
            "id": item.id,
            "task_id": item.task_id,
            "level": item.level,
            "message": item.message,
            "payload": item.payload_json,
            "created_at": item.created_at.isoformat() if item.created_at else "",
        }
