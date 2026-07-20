from __future__ import annotations

from dataclasses import field
from .._compat import slots_dataclass
from pathlib import Path
from sqlalchemy import func

from ..errors import NotFoundError, ValidationError
from ..models import Algorithm, Dataset, Sample
from ..plugins import PluginRunner
from .base import ServiceBase
from .sample_ordering import interleave_by_top_folder
from .training_compatibility import analyze_training_compatibility, build_dataset_summary


@slots_dataclass
class TrainingService(ServiceBase):
    task_manager: object
    task_repository: object
    algorithm_repository: object
    dataset_repository: object
    plugin_runner: PluginRunner = field(default_factory=PluginRunner)
    compatibility_cache: dict = field(default_factory=dict)

    def create_task(
        self,
        scenario_id: int,
        dataset_id: int,
        algorithm_id: int,
        parameters: dict,
    ) -> dict:
        if not algorithm_id:
            raise ValidationError("A training algorithm is required.")

        with self.session_factory() as session:
            dataset = session.query(Dataset).filter(Dataset.id == dataset_id).first()
            if dataset is None:
                raise NotFoundError(f"Dataset {dataset_id} not found.")
            if dataset.is_deleted or dataset.status == "deleted":
                raise ValidationError("Dataset must be active for training.")

            has_sample = (
                session.query(Sample.id)
                .filter(Sample.dataset_id == dataset.id, Sample.status != "deleted")
                .first()
            )
            if not has_sample:
                raise ValidationError("Dataset must contain at least one active sample.")

            algorithm = self.algorithm_repository.get_algorithm(session, algorithm_id)
            if not algorithm:
                raise NotFoundError(f"Algorithm {algorithm_id} not found.")
            if algorithm.category != "training":
                raise ValidationError("Algorithm must be a training algorithm.")
            if algorithm.status != "enabled":
                raise ValidationError("Algorithm must be enabled.")

            samples = (
                session.query(Sample)
                .filter(Sample.dataset_id == dataset.id, Sample.status != "deleted")
                .order_by(Sample.id.asc())
                .all()
            )
            compatibility = analyze_training_compatibility(dataset, samples, algorithm, parameters)
            compatibility = self._apply_custom_dataset_validator(
                dataset, samples, algorithm, compatibility
            )
            if not compatibility["compatible"]:
                raise ValidationError(f"数据集与训练算法不兼容：{compatibility['reason']}")

            resolved_parameters = {**(parameters or {}), "algorithm_id": algorithm.id}
            title = f"Training: {algorithm.name} on {dataset.name}"

            task = self.task_repository.create_task(
                session,
                task_type="training",
                status="pending",
                title=title,
                source_dataset_id=dataset.id,
                algorithm_id=algorithm.id,
                scenario_id=scenario_id if scenario_id else None,
                parameters_json=resolved_parameters,
                payload_json={
                    "dataset_id": dataset.id,
                    "algorithm_id": algorithm.id,
                    "scenario_id": scenario_id,
                },
                result_json={},
            )
            self.task_repository.add_task_log(session, task_id=task.id, level="info", message="Training task created")
            session.commit()
            return {
                "ok": True,
                "data": {"task_id": task.id, "status": task.status},
            }

    def get_compatibility(self, dataset_id: int) -> dict:
        with self.session_factory() as session:
            dataset = session.query(Dataset).filter(Dataset.id == dataset_id).first()
            if dataset is None or dataset.is_deleted or dataset.status == "deleted":
                raise NotFoundError(f"Dataset {dataset_id} not found.")
            sample_count, latest_sample_update = (
                session.query(func.count(Sample.id), func.max(Sample.updated_at))
                .filter(Sample.dataset_id == dataset.id, Sample.status != "deleted")
                .one()
            )
            algorithm_count, latest_algorithm_update = (
                session.query(func.count(Algorithm.id), func.max(Algorithm.updated_at))
                .filter(Algorithm.category == "training", Algorithm.status == "enabled")
                .one()
            )
            cache_key = (
                dataset.id,
                int(sample_count or 0),
                str(latest_sample_update or ""),
                str(dataset.updated_at or ""),
                int(algorithm_count or 0),
                str(latest_algorithm_update or ""),
            )
            cached = self.compatibility_cache.get(cache_key)
            if cached is not None:
                return cached
            samples = (
                session.query(Sample)
                .filter(Sample.dataset_id == dataset.id, Sample.status != "deleted")
                .order_by(Sample.id.asc())
                .all()
            )
            algorithms = self.algorithm_repository.list_algorithms(
                session, category="training", modality=""
            )
            items = []
            for algorithm in algorithms:
                if algorithm.status != "enabled":
                    continue
                result = analyze_training_compatibility(dataset, samples, algorithm)
                result = self._apply_custom_dataset_validator(
                    dataset, samples, algorithm, result
                )
                items.append(
                    {
                        "algorithm_id": algorithm.id,
                        "algorithm_key": algorithm.key,
                        "compatible": result["compatible"],
                        "reason": result["reason"],
                    }
                )
            result = {"dataset_id": dataset.id, "items": items}
            self.compatibility_cache = {
                key: value
                for key, value in self.compatibility_cache.items()
                if key[0] != dataset.id
            }
            self.compatibility_cache[cache_key] = result
            return result

    def _apply_custom_dataset_validator(self, dataset, samples, algorithm, result: dict) -> dict:
        rules = algorithm.validation_rules_json or {}
        if not result.get("compatible") or not rules.get("custom_dataset_validator"):
            return result
        try:
            callable_obj = self.plugin_runner.load_callable(
                module_path=algorithm.module_path or None,
                callable_name=algorithm.callable_name or None,
                script_path=algorithm.script_path or None,
            )
            validator = getattr(callable_obj, "__globals__", {}).get("validate_dataset")
            if not callable(validator):
                return {"compatible": False, "reason": "算法声明了自定义数据校验，但未找到 validate_dataset(summary)"}
            custom_result = validator(build_dataset_summary(dataset, samples))
            if isinstance(custom_result, bool):
                return {
                    "compatible": custom_result,
                    "reason": "自定义数据校验通过" if custom_result else "自定义数据校验未通过",
                }
            if not isinstance(custom_result, dict) or "compatible" not in custom_result:
                return {"compatible": False, "reason": "validate_dataset 必须返回 bool 或包含 compatible 的 dict"}
            return {
                "compatible": bool(custom_result.get("compatible")),
                "reason": str(custom_result.get("reason") or "自定义数据校验完成"),
            }
        except Exception as exc:
            return {"compatible": False, "reason": f"自定义数据校验执行失败：{exc}"}

    def run_task(self, task_id: int, context=None) -> dict:
        with self.session_factory() as session:
            task = self.task_repository.get_task_model(session, task_id)
            if task is None:
                raise NotFoundError(f"Task {task_id} not found.")
            if task.status != "running":
                raise ValidationError(f"Training task {task_id} cannot run from status '{task.status}'.")

            dataset = session.query(Dataset).filter(Dataset.id == task.source_dataset_id).first()
            if dataset is None or dataset.is_deleted or dataset.status == "deleted":
                raise ValidationError("Training dataset is not active.")

            algorithm = self.algorithm_repository.get_algorithm(session, task.algorithm_id)
            if not algorithm:
                raise NotFoundError(f"Algorithm {task.algorithm_id} not found.")
            if algorithm.category != "training":
                raise ValidationError("Algorithm must be a training algorithm.")

            samples = (
                session.query(Sample)
                .filter(Sample.dataset_id == dataset.id, Sample.status != "deleted")
                .order_by(Sample.id.asc())
                .all()
            )
            samples = interleave_by_top_folder(samples)
            if not samples:
                raise ValidationError("Dataset must contain at least one active sample.")

        plugin_context = context or self.task_manager.build_context(task_id)

        try:
            payload = {
                "task_id": task_id,
                "algorithm_key": algorithm.key,
                "category": "training",
                "modality": dataset.modality,
                "parameters": task.parameters_json,
                "input": {
                    "dataset_id": dataset.id,
                    "dataset_path": dataset.storage_path,
                    "samples": [self._serialize_sample(sample) for sample in samples],
                },
                "output": {
                    "output_dir": self.task_manager.get_output_dir(task_id),
                },
            }
            result = self.plugin_runner.run(
                payload,
                plugin_context,
                module_path=algorithm.module_path or None,
                callable_name=algorithm.callable_name or None,
                script_path=algorithm.script_path or None,
            )
            if not result.get("ok", False):
                error_code = result.get("error_code", "ALGORITHM_RUNTIME_ERROR")
                error_message = "训练任务已取消。" if error_code == "CANCELLED" else result.get("message", "Training plugin failed.")
                self.task_manager.fail(task_id, error_code=error_code, error_message=error_message)
                return {"ok": False, "error_code": error_code, "message": error_message}

            outputs = list(result.get("outputs", []))
            result_json = {
                "output_count": len(outputs),
                "artifacts": [o.get("artifact_path") for o in outputs if o.get("artifact_path")],
                "metrics": outputs[0].get("metrics", {}) if outputs else {},
                "summary": outputs[0].get("summary", "") if outputs else "",
            }
            self.task_manager.complete(task_id, result_json=result_json)
            return {"ok": True, "data": {"task_id": task_id, "output_count": len(outputs)}}
        except Exception as exc:
            self.task_manager.fail(task_id, error_code="ALGORITHM_RUNTIME_ERROR", error_message=str(exc))
            raise

    def _serialize_sample(self, sample: Sample) -> dict:
        return {
            "id": sample.id,
            "name": sample.name,
            "path": sample.file_path,
            "sample_path": sample.file_path,
            "relative_path": sample.relative_path,
            "status": sample.status,
            "metadata": sample.metadata_json,
            "labels": sample.labels_json or [],
        }
