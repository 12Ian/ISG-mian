from __future__ import annotations

from dataclasses import field
from .._compat import slots_dataclass

from ..errors import NotFoundError, ValidationError
from ..plugins import PluginRunner
from .base import ServiceBase


@slots_dataclass
class AlgorithmService(ServiceBase):
    algorithm_repository: object
    log_repository: object
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

    def _require_algorithm(self, session, algorithm_id: int):
        algorithm = self.algorithm_repository.get_algorithm(session, algorithm_id)
        if not algorithm:
            raise NotFoundError(f"Algorithm {algorithm_id} not found.")
        return algorithm

    def _serialize_algorithm(self, session, algorithm) -> dict:
        return {
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
            "validation_rules": algorithm.validation_rules_json,
            "parameters": [
                {
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
                for item in self.algorithm_repository.list_parameters(session, algorithm.id)
            ],
        }

    def _merge_validation_rules(self, payload: dict, existing: dict | None = None) -> dict:
        rules = dict(existing or {})
        if "validation_rules" in payload and isinstance(payload["validation_rules"], dict):
            rules.update(payload["validation_rules"])
        for field_name in ["runtime_artifact_path", "dataset_path", "label_path", "test_path", "model_path"]:
            if payload.get(field_name):
                rules[field_name] = payload[field_name]
        return rules
