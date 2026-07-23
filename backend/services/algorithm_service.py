from __future__ import annotations

from dataclasses import field
from pathlib import Path
from .._compat import slots_dataclass

from ..errors import NotFoundError, ValidationError
from ..models import CleaningSuggestion, EvaluationResult, GenerationOutput, Task
from ..parameter_ranges import (
    default_parameter_sampling_range,
    normalized_parameter_range,
    parameter_display_precision,
)
from ..plugins import PluginRunner
from ..plugins.reflector import validate_parameters
from core.data_management.dataset_requirements import normalize_dataset_requirements
from .base import ServiceBase


@slots_dataclass
class AlgorithmService(ServiceBase):
    algorithm_repository: object
    log_repository: object
    model_asset_service: object | None = None
    plugin_runner: PluginRunner = field(default_factory=PluginRunner)

    def create_algorithm(self, payload: dict) -> dict:
        self._validate_payload(payload, creating=True)
        with self.session_factory() as session:
            validation_rules = self._merge_validation_rules(payload)
            if self.algorithm_repository.get_algorithm_by_key(session, payload["key"]):
                raise ValidationError(f"Algorithm key already exists: {payload['key']}")
            algorithm = self.algorithm_repository.create_algorithm(
                session,
                key=payload["key"],
                name=payload["name"],
                category=payload["category"],
                modality=payload["modality"],
                status="enabled",
                entry_type=payload["entry_type"],
                module_path=payload.get("module_path"),
                callable_name=payload.get("callable_name"),
                script_path=payload.get("script_path"),
                executable_path=payload.get("executable_path"),
                input_contract_json=payload.get("input_contract", {}),
                output_contract_json=payload.get("output_contract", {}),
                validation_rules_json=validation_rules,
            )
            self.algorithm_repository.replace_parameters(session, algorithm.id, payload.get("parameters", []))
            self.log_repository.add(
                session,
                level="info",
                action="create_algorithm",
                resource_type="algorithm",
                resource_id=str(algorithm.id),
                message=f"Created algorithm {algorithm.key}",
            )
            session.commit()
            return {"ok": True, "data": self._serialize_algorithm(session, algorithm)}

    def update_algorithm(self, algorithm_id: int, payload: dict) -> dict:
        if "parameters" in payload:
            valid, error = validate_parameters(payload["parameters"])
            if not valid:
                raise ValidationError(f"算法参数配置错误：{error}")
        with self.session_factory() as session:
            algorithm = self._require_algorithm(session, algorithm_id)
            validation_rules = self._merge_validation_rules(payload, existing=algorithm.validation_rules_json or {})
            for field_name, attr_name in {
                "name": "name",
                "category": "category",
                "modality": "modality",
                "entry_type": "entry_type",
                "module_path": "module_path",
                "callable_name": "callable_name",
                "script_path": "script_path",
                "executable_path": "executable_path",
            }.items():
                if field_name in payload:
                    setattr(algorithm, attr_name, payload[field_name])
            if "input_contract" in payload:
                algorithm.input_contract_json = payload["input_contract"]
            if "output_contract" in payload:
                algorithm.output_contract_json = payload["output_contract"]
            if validation_rules is not None:
                algorithm.validation_rules_json = validation_rules
            if "parameters" in payload:
                self.algorithm_repository.replace_parameters(session, algorithm.id, payload["parameters"])
            self.log_repository.add(
                session,
                level="info",
                action="update_algorithm",
                resource_type="algorithm",
                resource_id=str(algorithm.id),
                message=f"Updated algorithm {algorithm.key}",
            )
            session.commit()
            return {"ok": True, "data": self._serialize_algorithm(session, algorithm)}

    def delete_algorithm(self, algorithm_id: int) -> dict:
        with self.session_factory() as session:
            algorithm = self._require_algorithm(session, algorithm_id)
            active_task = None
            for candidate in session.query(Task).filter(Task.status.in_(["pending", "running"])).all():
                referenced_ids = set((candidate.parameters_json or {}).get("algorithm_ids", []))
                referenced_ids.update((candidate.payload_json or {}).get("algorithm_ids", []))
                if candidate.algorithm_id == algorithm_id or algorithm_id in referenced_ids:
                    active_task = candidate
                    break
            if active_task is not None:
                raise ValidationError(f"算法正在被任务 {active_task.id} 使用，不能卸载。")
            # 级联清理绑定关系
            self.algorithm_repository.delete_bindings_for_algorithm(session, algorithm_id)
            session.query(Task).filter(Task.algorithm_id == algorithm_id).update(
                {Task.algorithm_id: None}, synchronize_session=False
            )
            session.query(CleaningSuggestion).filter(CleaningSuggestion.algorithm_id == algorithm_id).update(
                {CleaningSuggestion.algorithm_id: None}, synchronize_session=False
            )
            session.query(GenerationOutput).filter(GenerationOutput.algorithm_id == algorithm_id).update(
                {GenerationOutput.algorithm_id: None}, synchronize_session=False
            )
            session.query(EvaluationResult).filter(EvaluationResult.algorithm_id == algorithm_id).update(
                {EvaluationResult.algorithm_id: None}, synchronize_session=False
            )
            for task in session.query(Task).all():
                parameters = dict(task.parameters_json or {})
                payload = dict(task.payload_json or {})
                changed = False
                for container in (parameters, payload):
                    ids = list(container.get("algorithm_ids", []))
                    filtered_ids = [item for item in ids if item != algorithm_id]
                    if filtered_ids != ids:
                        container["algorithm_ids"] = filtered_ids
                        changed = True
                scopes = dict(parameters.get("algorithm_parameters", {}) or {})
                if str(algorithm_id) in scopes or algorithm_id in scopes:
                    scopes.pop(str(algorithm_id), None)
                    scopes.pop(algorithm_id, None)
                    parameters["algorithm_parameters"] = scopes
                    changed = True
                if changed:
                    task.parameters_json = parameters
                    task.payload_json = payload
            self.algorithm_repository.replace_parameters(session, algorithm_id, [])
            session.delete(algorithm)
            self.log_repository.add(
                session,
                level="info",
                action="delete_algorithm",
                resource_type="algorithm",
                resource_id=str(algorithm_id),
                message=f"Deleted algorithm {algorithm.key}",
            )
            session.commit()
            return {"ok": True, "data": {"id": algorithm_id}}

    def set_algorithm_enabled(self, algorithm_id: int, enabled: bool) -> dict:
        with self.session_factory() as session:
            algorithm = self._require_algorithm(session, algorithm_id)
            algorithm.status = "enabled" if enabled else "disabled"
            self.log_repository.add(
                session,
                level="info",
                action="set_algorithm_enabled",
                resource_type="algorithm",
                resource_id=str(algorithm.id),
                message=f"Set algorithm {algorithm.key} to {algorithm.status}",
            )
            session.commit()
            return {"ok": True, "data": self._serialize_algorithm(session, algorithm)}

    def validate_algorithm(self, algorithm_id: int) -> dict:
        with self.session_factory() as session:
            algorithm = self._require_algorithm(session, algorithm_id)
            callable_obj = self.plugin_runner.load_callable(
                module_path=algorithm.module_path,
                callable_name=algorithm.callable_name,
                script_path=algorithm.script_path,
            )
            data = self._serialize_algorithm(session, algorithm)
            data["validated_entry"] = getattr(callable_obj, "__name__", callable_obj.__class__.__name__)
            return {"ok": True, "data": data}

    def get_algorithms(self, category: str, modality: str) -> list[dict]:
        with self.session_factory() as session:
            algorithms = self.algorithm_repository.list_algorithms(session, category=category or "", modality=modality or "")
            return [self._serialize_algorithm(session, algorithm) for algorithm in algorithms]

    def _validate_payload(self, payload: dict, *, creating: bool) -> None:
        required = ["name", "category", "modality", "entry_type"]
        if creating:
            required.append("key")
        for field_name in required:
            if not payload.get(field_name):
                raise ValidationError(f"Algorithm field is required: {field_name}")
        if not payload.get("module_path") and not payload.get("script_path"):
            raise ValidationError("Either module_path or script_path is required.")
        if not payload.get("callable_name"):
            raise ValidationError("callable_name is required.")
        valid, error = validate_parameters(payload.get("parameters", []))
        if not valid:
            raise ValidationError(f"算法参数配置错误：{error}")

    def _require_algorithm(self, session, algorithm_id: int):
        algorithm = self.algorithm_repository.get_algorithm(session, algorithm_id)
        if not algorithm:
            raise NotFoundError(f"Algorithm {algorithm_id} not found.")
        return algorithm

    def _serialize_algorithm(self, session, algorithm) -> dict:
        data = {
            "id": algorithm.id,
            "key": algorithm.key,
            "name": algorithm.name,
            "category": algorithm.category,
            "modality": algorithm.modality,
            "status": algorithm.status,
            "entry_type": algorithm.entry_type,
            "module_path": algorithm.module_path or "",
            "callable_name": algorithm.callable_name or "",
            "script_path": algorithm.script_path or "",
            "input_contract": algorithm.input_contract_json,
            "output_contract": algorithm.output_contract_json,
            "supports_pipeline": self._supports_pipeline(algorithm),
            "pipeline_position": self._pipeline_position(algorithm),
            "validation_rules": algorithm.validation_rules_json,
            "parameters": [
                self._serialize_parameter(item)
                for item in self.algorithm_repository.list_parameters(session, algorithm.id)
            ],
        }
        self._append_model_asset_options(data)
        # 训练算法：内嵌绑定的评估算法信息
        if algorithm.category == "training":
            binding = self.algorithm_repository.get_binding_for_training(session, algorithm.id)
            if binding:
                eval_algo = self.algorithm_repository.get_algorithm(session, binding.evaluation_algorithm_id)
                if eval_algo:
                    data["bound_evaluation_key"] = eval_algo.key
                    data["bound_evaluation_name"] = eval_algo.name
        return data

    def _append_model_asset_options(self, data: dict) -> None:
        if self.model_asset_service is None or data.get("category") != "training":
            return
        family = self.model_asset_service.family_for_algorithm_key(data.get("key", ""))
        if not family:
            return
        model_paths = self.model_asset_service.paths_for_family(family)
        if not model_paths:
            return
        model_parameter_names = {
            "weights",
            "weight",
            "weights_path",
            "model",
            "model_path",
            "model_yaml",
            "model_cfg",
            "cfg",
            "checkpoint",
            "pretrained",
            "pretrained_weights",
        }
        for parameter in data.get("parameters", []):
            parameter_name = str(parameter.get("name") or "").casefold()
            if parameter_name not in model_parameter_names:
                continue
            options = list(parameter.get("options") or [])
            for model_path in model_paths:
                suffix = Path(model_path).suffix.casefold()
                if parameter_name in {"weights", "weight", "weights_path", "pretrained", "pretrained_weights"}:
                    if suffix not in {".pt", ".pth"}:
                        continue
                elif parameter_name in {"model_yaml", "model_cfg", "cfg"}:
                    if suffix not in {".yaml", ".yml"}:
                        continue
                elif suffix not in {".pt", ".pth", ".yaml", ".yml"}:
                    continue
                replaced = False
                model_name = Path(model_path).name.casefold()
                for index, option in enumerate(options):
                    if Path(str(option)).name.casefold() == model_name:
                        options[index] = model_path
                        replaced = True
                        break
                if not replaced and model_path not in options:
                    options.append(model_path)
            parameter["options"] = options

    def _serialize_parameter(self, item) -> dict:
        base = {
            "name": item.name,
            "label": item.label,
            "type": item.type,
            "required": item.required,
            "default_value": item.default_value,
            "min_value": item.min_value,
            "max_value": item.max_value,
            "options": item.options_json,
            "description": item.description,
        }
        range_info = normalized_parameter_range(base)
        base["min_value"] = range_info["min_value"]
        base["max_value"] = range_info["max_value"]
        base["options"] = range_info["options"]
        base["display_precision"] = parameter_display_precision(base)
        sampling_range = default_parameter_sampling_range(base)
        if sampling_range is not None:
            base["suggested_min_value"] = sampling_range["min"]
            base["suggested_max_value"] = sampling_range["max"]
        return base

    def _supports_pipeline(self, algorithm) -> bool:
        input_contract = algorithm.input_contract_json or {}
        output_contract = algorithm.output_contract_json or {}
        if input_contract.get("supports_pipeline") is False or output_contract.get("supports_pipeline") is False:
            return False
        if input_contract.get("supports_pipeline") is True or output_contract.get("supports_pipeline") is True:
            return True
        if algorithm.category != "generation" or algorithm.modality not in {"image", "multimodal"}:
            return False
        artifact_types = set(output_contract.get("artifact_types") or [])
        produces = set(output_contract.get("produces") or [])
        standalone_tokens = ("gan", "diffusion", "wgan", "mae", "vit")
        if any(token in (algorithm.key or "").lower() for token in standalone_tokens):
            return False
        return "image" in artifact_types or "generated_samples" in produces or "outputs" in produces

    def _pipeline_position(self, algorithm) -> str:
        input_contract = algorithm.input_contract_json or {}
        output_contract = algorithm.output_contract_json or {}
        return input_contract.get("pipeline_position") or output_contract.get("pipeline_position") or (
            "any" if self._supports_pipeline(algorithm) else "standalone"
        )

    def _merge_validation_rules(self, payload: dict, existing: dict | None = None) -> dict:
        rules = dict(existing or {})
        # 兼容两种键名：QML UI 传入 "validation_rules"，种子数据使用 "validation_rules_json"
        vr = payload.get("validation_rules") or payload.get("validation_rules_json")
        if isinstance(vr, dict):
            rules.update(vr)
        requirements = payload.get("dataset_requirements")
        if requirements is None and isinstance(vr, dict) and "dataset_requirements" in vr:
            requirements = vr.get("dataset_requirements")
        if requirements is not None:
            try:
                rules["dataset_requirements"] = normalize_dataset_requirements(requirements)
            except ValueError as exc:
                raise ValidationError(f"数据集要求配置错误：{exc}") from exc
        for field_name in ["runtime_artifact_path", "dataset_path", "label_path", "test_path", "model_path"]:
            if payload.get(field_name):
                rules[field_name] = payload[field_name]
        return rules

    # ── 训练-评估算法绑定 ─────────────────────────────────────

    def get_bindings(self) -> dict:
        """返回 {training_key: evaluation_key} 映射，供 QML 直接使用。"""
        with self.session_factory() as session:
            bindings = self.algorithm_repository.get_all_bindings(session)
            result = {}
            for binding in bindings:
                training_algo = self.algorithm_repository.get_algorithm(session, binding.training_algorithm_id)
                eval_algo = self.algorithm_repository.get_algorithm(session, binding.evaluation_algorithm_id)
                if training_algo and eval_algo:
                    result[training_algo.key] = eval_algo.key
            return result

    def set_binding(self, training_key: str, evaluation_key: str) -> dict:
        """设置训练算法到评估算法的绑定。evaluation_key 为空字符串时解绑。"""
        with self.session_factory() as session:
            training_algo = self.algorithm_repository.get_algorithm_by_key(session, training_key)
            if not training_algo:
                raise NotFoundError(f"Training algorithm not found: {training_key}")
            if training_algo.category != "training":
                raise ValidationError("Algorithm must be a training algorithm.")

            if not evaluation_key:
                self.algorithm_repository.delete_binding_for_training(session, training_algo.id)
                session.commit()
                return {"ok": True, "data": {"training_key": training_key, "evaluation_key": None}}

            eval_algo = self.algorithm_repository.get_algorithm_by_key(session, evaluation_key)
            if not eval_algo:
                raise NotFoundError(f"Evaluation algorithm not found: {evaluation_key}")
            if eval_algo.category != "evaluation":
                raise ValidationError("Algorithm must be an evaluation algorithm.")

            self.algorithm_repository.set_binding(session, training_algo.id, eval_algo.id)
            session.commit()
            return {"ok": True, "data": {"training_key": training_key, "evaluation_key": evaluation_key}}

    def delete_binding(self, training_key: str) -> dict:
        with self.session_factory() as session:
            training_algo = self.algorithm_repository.get_algorithm_by_key(session, training_key)
            if not training_algo:
                raise NotFoundError(f"Training algorithm not found: {training_key}")
            deleted = self.algorithm_repository.delete_binding_for_training(session, training_algo.id)
            session.commit()
            return {"ok": True, "data": {"training_key": training_key, "deleted": deleted}}
