from __future__ import annotations

from dataclasses import field
from .._compat import slots_dataclass
from pathlib import Path

from core.sample_generation.detection_label_transform import has_detection_labels
from core.data_management.multimodal_association import (
    sample_group_id,
    sample_metadata,
    sample_role,
)

from ..errors import NotFoundError, ValidationError
from ..models import Algorithm, Dataset, GenerationOutput, Sample
from ..parameter_ranges import normalize_parameter_value
from ..plugins import PluginRunner
from ..storage import FileIndexer
from .base import ServiceBase
from .sample_ordering import interleave_by_top_folder


@slots_dataclass
class GenerationService(ServiceBase):
    task_manager: object
    task_repository: object
    algorithm_repository: object
    dataset_repository: object
    plugin_runner: PluginRunner = field(default_factory=PluginRunner)
    file_indexer: FileIndexer = field(default_factory=FileIndexer)

    def create_task(
        self,
        source_dataset_id: int,
        target_dataset_id: int,
        algorithm_ids: list[int],
        parameters: dict,
        target_count: int,
    ) -> dict:
        if not algorithm_ids:
            raise ValidationError("At least one generation algorithm is required.")
        if target_count <= 0:
            raise ValidationError("target_count must be greater than zero.")

        with self.session_factory() as session:
            source_dataset = session.query(Dataset).filter(Dataset.id == source_dataset_id).first()
            if source_dataset is None:
                raise NotFoundError(f"Dataset {source_dataset_id} not found.")
            if source_dataset.is_deleted or source_dataset.status == "deleted":
                raise ValidationError("Source dataset must be active for generation.")

            source_samples = (
                session.query(Sample)
                .filter(Sample.dataset_id == source_dataset.id, Sample.status != "deleted")
                .order_by(Sample.id.asc())
                .all()
            )
            source_samples = [sample for sample in source_samples if self._is_generation_input_sample(sample, source_dataset.modality)]
            source_samples = interleave_by_top_folder(source_samples)
            if not source_samples:
                raise ValidationError("Source dataset must contain at least one active sample.")

            generation_mode = str((parameters or {}).get("generation_mode") or "independent")
            if generation_mode not in {"independent", "pipeline"}:
                raise ValidationError("generation_mode must be 'independent' or 'pipeline'.")
            algorithms: list[Algorithm] = []
            for algorithm_id in algorithm_ids:
                algorithm = self.algorithm_repository.get_algorithm(session, algorithm_id)
                if not algorithm:
                    raise NotFoundError(f"Algorithm {algorithm_id} not found.")
                if algorithm.category != "generation":
                    raise ValidationError("All algorithms must be generation algorithms.")
                if algorithm.status != "enabled":
                    raise ValidationError("All algorithms must be enabled.")
                if not self._algorithm_matches_dataset(algorithm.modality, source_dataset.modality, generation_mode):
                    raise ValidationError("Algorithm modality must match the source dataset modality.")
                if self._unsafe_for_multimodal_companions(algorithm.key, source_dataset.modality):
                    raise ValidationError(f"算法 {algorithm.name} 会改变空间位置，暂不能与多模态 mask/雷达安全同步。")
                algorithms.append(algorithm)

            target_dataset = self._resolve_target_dataset(session, source_dataset, target_dataset_id)
            resolved_algorithm_ids = [algorithm.id for algorithm in algorithms]
            if generation_mode == "pipeline":
                for algorithm in algorithms:
                    if not self._supports_pipeline(algorithm, source_dataset.modality):
                        raise ValidationError(f"Algorithm {algorithm.name} does not support pipeline generation.")

            resolved_parameters = self._normalize_task_parameters(session, algorithms, parameters)
            resolved_parameters["algorithm_ids"] = resolved_algorithm_ids
            resolved_parameters["target_count"] = target_count
            resolved_parameters["generation_mode"] = generation_mode

            task = self.task_repository.create_task(
                session,
                task_type="generation",
                status="pending",
                title="",
                source_dataset_id=source_dataset.id,
                target_dataset_id=target_dataset.id,
                algorithm_id=algorithms[0].id,
                parameters_json=resolved_parameters,
                payload_json={
                    "source_dataset_id": source_dataset.id,
                    "target_dataset_id": target_dataset.id,
                    "algorithm_ids": resolved_algorithm_ids,
                    "target_count": target_count,
                    "generation_mode": generation_mode,
                },
                result_json={},
            )
            task.title = f"生成任务_{source_dataset.name}_#{task.id}"
            self.task_repository.add_task_log(session, task_id=task.id, level="info", message="Generation task created")
            session.commit()
            return {
                "ok": True,
                "data": {
                    "task_id": task.id,
                    "status": task.status,
                    "target_dataset_id": target_dataset.id,
                    "target_dataset_name": target_dataset.name,
                },
            }

    def create_generation_task(
        self,
        source_dataset_id: int,
        target_dataset_id: int,
        algorithm_ids: list[int],
        parameters: dict,
        target_count: int,
    ) -> dict:
        return self.create_task(source_dataset_id, target_dataset_id, algorithm_ids, parameters, target_count)

    def _normalize_task_parameters(self, session, algorithms: list[Algorithm], parameters: dict | None) -> dict:
        normalized = dict(parameters or {})
        for algorithm in algorithms:
            for item in self.algorithm_repository.list_parameters(session, algorithm.id):
                parameter = {
                    "name": item.name,
                    "type": item.type,
                    "default_value": item.default_value,
                    "min_value": item.min_value,
                    "max_value": item.max_value,
                    "options": item.options_json,
                }
                normalized[item.name] = normalize_parameter_value(parameter, normalized.get(item.name, item.default_value))
        return normalized

    def run_task(self, task_id: int, context=None) -> dict:
        with self.session_factory() as session:
            task = self.task_repository.get_task_model(session, task_id)
            if task is None:
                raise NotFoundError(f"Task {task_id} not found.")
            if task.status != "running":
                raise ValidationError(f"Generation task {task_id} cannot run from status '{task.status}'.")

            source_dataset = session.query(Dataset).filter(Dataset.id == task.source_dataset_id).first()
            target_dataset = session.query(Dataset).filter(Dataset.id == task.target_dataset_id).first()
            if source_dataset is None or source_dataset.is_deleted or source_dataset.status == "deleted":
                raise ValidationError("Generation source dataset is not active.")
            if target_dataset is None or target_dataset.is_deleted or target_dataset.status == "deleted":
                raise ValidationError("Generation target dataset is not active.")

            algorithm_ids = list(task.payload_json.get("algorithm_ids", []))
            target_count = int(task.payload_json.get("target_count", 0))
            generation_mode = str(task.payload_json.get("generation_mode") or task.parameters_json.get("generation_mode") or "independent")
            if target_count <= 0:
                raise ValidationError("Generation task target_count must be greater than zero.")

            algorithms: list[Algorithm] = []
            for algorithm_id in algorithm_ids:
                algorithm = self.algorithm_repository.get_algorithm(session, algorithm_id)
                if not algorithm:
                    raise NotFoundError(f"Algorithm {algorithm_id} not found.")
                if algorithm.category != "generation":
                    raise ValidationError("All algorithms must be generation algorithms.")
                if algorithm.status != "enabled":
                    raise ValidationError("All algorithms must be enabled.")
                if not self._algorithm_matches_dataset(algorithm.modality, source_dataset.modality, generation_mode):
                    raise ValidationError("Algorithm modality must match the source dataset modality.")
                if self._unsafe_for_multimodal_companions(algorithm.key, source_dataset.modality):
                    raise ValidationError(f"算法 {algorithm.name} 会改变空间位置，暂不能与多模态 mask/雷达安全同步。")
                if generation_mode == "pipeline" and not self._supports_pipeline(algorithm, source_dataset.modality):
                    raise ValidationError(f"Algorithm {algorithm.name} does not support pipeline generation.")
                algorithms.append(algorithm)

            source_samples = (
                session.query(Sample)
                .filter(Sample.dataset_id == source_dataset.id, Sample.status != "deleted")
                .order_by(Sample.id.asc())
                .all()
            )
            source_samples = [sample for sample in source_samples if self._is_generation_input_sample(sample, source_dataset.modality)]
            source_samples = interleave_by_top_folder(source_samples)
            if not source_samples:
                raise ValidationError("Source dataset must contain at least one active sample.")

        plugin_context = context or self.task_manager.build_context(task_id)
        if generation_mode == "pipeline":
            return self._run_pipeline_task(
                task_id=task_id,
                source_dataset=source_dataset,
                target_dataset=target_dataset,
                source_samples=source_samples,
                algorithms=algorithms,
                target_count=target_count,
                plugin_context=plugin_context,
                task_parameters=task.parameters_json,
            )

        algorithm_count = len(algorithms)
        base_count = target_count // algorithm_count
        extra_count = target_count % algorithm_count
        target_counts_by_algorithm = [
            base_count + (1 if index < extra_count else 0)
            for index in range(algorithm_count)
        ]

        pending_outputs: list[tuple[int, list[dict]]] = []
        produced_count = 0
        try:
            for algorithm, algorithm_target_count in zip(algorithms, target_counts_by_algorithm):
                if algorithm_target_count <= 0:
                    continue
                algorithm_samples = self._samples_for_algorithm(
                    source_samples, source_dataset.modality, algorithm.modality
                )
                if not algorithm_samples:
                    raise ValidationError(f"算法 {algorithm.name} 没有可用的输入样本。")
                payload = {
                    "task_id": task_id,
                    "algorithm_key": algorithm.key,
                    "category": "generation",
                    "modality": source_dataset.modality,
                    "parameters": task.parameters_json,
                    "target_count": algorithm_target_count,
                    "input": {
                        "dataset_id": source_dataset.id,
                        "dataset_path": source_dataset.storage_path,
                        "samples": [self._serialize_sample(sample) for sample in algorithm_samples],
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
                    error_message = "生成任务已取消。" if error_code == "CANCELLED" else result.get("message", "Generation plugin failed.")
                    self.task_manager.fail(task_id, error_code=error_code, error_message=error_message)
                    return {"ok": False, "error_code": error_code, "message": error_message}

                outputs = list(result.get("outputs", []))[:algorithm_target_count]
                pending_outputs.append((algorithm.id, outputs))
                produced_count += len(outputs)
                progress_pct = min(produced_count / target_count * 100.0, 99.0)
                self.task_manager.set_progress(task_id, progress_pct, f"Produced {produced_count}/{target_count}")

            if produced_count < target_count:
                import logging
                logging.getLogger("isg").warning(
                    f"Generation task {task_id}: produced {produced_count}/{target_count}, "
                    f"{target_count - produced_count} samples skipped. Continuing with available outputs."
                )

            for algorithm_id, outputs in pending_outputs:
                self._persist_generation_outputs(
                    task_id=task_id,
                    target_dataset_id=target_dataset.id,
                    algorithm_id=algorithm_id,
                    outputs=outputs,
                )

            source_copied_count = self._persist_source_outputs(
                task_id=task_id,
                target_dataset_id=target_dataset.id,
                source_samples=source_samples,
            )

            total_count = produced_count + source_copied_count
            self.task_manager.complete(
                task_id,
                result_json={
                    "generated_count": produced_count,
                    "source_copied_count": source_copied_count,
                    "total_count": total_count,
                    "target_dataset_id": target_dataset.id,
                },
            )
            return {
                "ok": True,
                "data": {
                    "task_id": task_id,
                    "generated_count": produced_count,
                    "source_copied_count": source_copied_count,
                    "total_count": total_count,
                    "target_dataset_id": target_dataset.id,
                },
            }
        except Exception as exc:
            self.task_manager.fail(task_id, error_code="ALGORITHM_RUNTIME_ERROR", error_message=str(exc))
            raise

    def _run_pipeline_task(
        self,
        *,
        task_id: int,
        source_dataset: Dataset,
        target_dataset: Dataset,
        source_samples: list[Sample],
        algorithms: list[Algorithm],
        target_count: int,
        plugin_context,
        task_parameters: dict,
    ) -> dict:
        current_samples = [self._serialize_sample(sample) for sample in source_samples]
        final_algorithm_id = algorithms[-1].id
        pipeline_keys = [algorithm.key for algorithm in algorithms]
        produced_count = 0

        try:
            for index, algorithm in enumerate(algorithms):
                if not current_samples:
                    break
                stage_dir = Path(self.task_manager.get_output_dir(task_id)) / f"pipeline_{index + 1:02d}_{algorithm.id}"
                stage_target_count = target_count if index == 0 else len(current_samples)
                payload = {
                    "task_id": task_id,
                    "algorithm_key": algorithm.key,
                    "category": "generation",
                    "modality": source_dataset.modality,
                    "parameters": task_parameters,
                    "target_count": stage_target_count,
                    "input": {
                        "dataset_id": source_dataset.id,
                        "dataset_path": source_dataset.storage_path,
                        "samples": current_samples,
                    },
                    "output": {
                        "output_dir": str(stage_dir),
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
                    error_message = "生成任务已取消。" if error_code == "CANCELLED" else result.get("message", "Generation plugin failed.")
                    self.task_manager.fail(task_id, error_code=error_code, error_message=error_message)
                    return {"ok": False, "error_code": error_code, "message": error_message}

                outputs = list(result.get("outputs", []))[:stage_target_count]
                current_samples = self._outputs_as_pipeline_samples(outputs, current_samples, algorithm)
                produced_count = len(current_samples) if index == len(algorithms) - 1 else 0
                progress_pct = min(((index + 1) / len(algorithms)) * 99.0, 99.0)
                self.task_manager.set_progress(
                    task_id,
                    progress_pct,
                    f"Pipeline step {index + 1}/{len(algorithms)} produced {len(current_samples)} samples",
                )

            final_outputs = current_samples[:target_count]
            for output in final_outputs:
                metadata = dict(output.get("metadata", {}) or {})
                metadata["generation_mode"] = "pipeline"
                metadata["pipeline_algorithms"] = pipeline_keys
                metadata["final_algorithm_key"] = algorithms[-1].key
                output["metadata"] = metadata

            produced_count = len(final_outputs)
            if produced_count < target_count:
                import logging
                logging.getLogger("isg").warning(
                    f"Generation pipeline task {task_id}: produced {produced_count}/{target_count}, "
                    f"{target_count - produced_count} samples skipped. Continuing with available outputs."
                )

            self._persist_generation_outputs(
                task_id=task_id,
                target_dataset_id=target_dataset.id,
                algorithm_id=final_algorithm_id,
                outputs=final_outputs,
            )

            source_copied_count = self._persist_source_outputs(
                task_id=task_id,
                target_dataset_id=target_dataset.id,
                source_samples=source_samples,
            )
            total_count = produced_count + source_copied_count
            self.task_manager.complete(
                task_id,
                result_json={
                    "generated_count": produced_count,
                    "source_copied_count": source_copied_count,
                    "total_count": total_count,
                    "target_dataset_id": target_dataset.id,
                    "generation_mode": "pipeline",
                    "pipeline_algorithms": pipeline_keys,
                },
            )
            return {
                "ok": True,
                "data": {
                    "task_id": task_id,
                    "generated_count": produced_count,
                    "source_copied_count": source_copied_count,
                    "total_count": total_count,
                    "target_dataset_id": target_dataset.id,
                    "generation_mode": "pipeline",
                },
            }
        except Exception as exc:
            self.task_manager.fail(task_id, error_code="ALGORITHM_RUNTIME_ERROR", error_message=str(exc))
            raise

    def _outputs_as_pipeline_samples(self, outputs: list[dict], input_samples: list[dict], algorithm: Algorithm) -> list[dict]:
        input_by_id = {item.get("id"): item for item in input_samples}
        result = []
        for index, output in enumerate(outputs):
            output_path = output.get("output_path") or output.get("sample_path") or output.get("path")
            if not output_path:
                continue
            source_sample_id = output.get("source_sample_id")
            positional_sample = input_samples[index] if index < len(input_samples) else None
            if positional_sample is not None and (
                source_sample_id is None or positional_sample.get("id") == source_sample_id
            ):
                source_sample = positional_sample
            else:
                source_sample = input_by_id.get(source_sample_id) or positional_sample
            original_source_sample_id = (
                output.get("original_source_sample_id")
                or (source_sample or {}).get("original_source_sample_id")
                or (source_sample or {}).get("source_sample_id")
                or source_sample_id
            )
            metadata = dict(output.get("metadata", {}) or {})
            previous_chain = list((source_sample or {}).get("pipeline_algorithms", []))
            pipeline_algorithms = previous_chain + [algorithm.key]
            metadata["pipeline_algorithms"] = pipeline_algorithms
            labels, label_policy = self._resolve_output_labels(
                output,
                (source_sample or {}).get("labels", []),
            )
            result.append(
                {
                    "id": original_source_sample_id,
                    "name": Path(output_path).name,
                    "path": output_path,
                    "sample_path": output_path,
                    "modality": (source_sample or {}).get("modality"),
                    "sample_type": (source_sample or {}).get("sample_type"),
                    "relative_path": output.get("relative_path") or Path(output_path).name,
                    "metadata": metadata,
                    "labels": labels,
                    "label_policy": label_policy,
                    "source_sample_id": original_source_sample_id,
                    "original_source_sample_id": original_source_sample_id,
                    "pipeline_algorithms": pipeline_algorithms,
                    "output_path": output_path,
                    "status": output.get("status", "created"),
                }
            )
        return result

    def list_outputs(self, task_id: int, status: str | None, page: int, page_size: int) -> dict:
        with self.session_factory() as session:
            task = self.task_repository.get_task_model(session, task_id)
            if task is None:
                raise NotFoundError(f"Task {task_id} not found.")
            query = session.query(GenerationOutput).filter(GenerationOutput.task_id == task_id)
            if status:
                query = query.filter(GenerationOutput.status == status)
            total = query.count()
            items = (
                query.order_by(GenerationOutput.created_at.asc(), GenerationOutput.id.asc())
                .offset(max(page - 1, 0) * page_size)
                .limit(page_size)
                .all()
            )
            parameters = dict(task.parameters_json or {})
            parameters.pop("algorithm_ids", None)
            return {
                "total": total,
                "items": [self._serialize_generation_output(session, item) for item in items],
                "parameters": parameters,
                "page": max(page, 1),
                "page_size": max(page_size, 1),
            }

    def get_generation_outputs(self, task_id: int, status: str | None, page: int, page_size: int) -> dict:
        return self.list_outputs(task_id, status, page, page_size)

    def _resolve_target_dataset(self, session, source_dataset: Dataset, target_dataset_id: int) -> Dataset:
        if target_dataset_id:
            target_dataset = session.query(Dataset).filter(Dataset.id == target_dataset_id).first()
            if target_dataset is None:
                raise NotFoundError(f"Dataset {target_dataset_id} not found.")
            if target_dataset.is_deleted or target_dataset.status == "deleted":
                raise ValidationError("Target dataset must be active for generation.")
            if target_dataset.modality != source_dataset.modality:
                raise ValidationError("Target dataset modality must match the source dataset modality.")
            return target_dataset

        target_dataset = self.dataset_repository.create_dataset(
            session,
            name=f"Generated from {source_dataset.name}",
            modality=source_dataset.modality,
            description=f"Auto-created target dataset for source dataset {source_dataset.id}",
            status="generated",
            parent_dataset_id=source_dataset.id,
            storage_path="",
            tags_json=["generated"],
            extra_json={"source_dataset_id": source_dataset.id, "dataset_stage": "generated"},
        )
        target_dataset.storage_path = str(self._allocate_dataset_dir(target_dataset.id, target_dataset.name))
        return target_dataset

    def _persist_generation_outputs(self, *, task_id: int, target_dataset_id: int, algorithm_id: int, outputs: list[dict]) -> list[dict]:
        if not outputs:
            return []

        persisted_items: list[dict] = []
        multimodal_indexes: dict[int, dict[str, list[Sample]]] = {}
        with self.session_factory() as session:
            target_dataset = session.query(Dataset).filter(Dataset.id == target_dataset_id).first()
            if target_dataset is None:
                raise NotFoundError(f"Dataset {target_dataset_id} not found.")

            for output in outputs:
                output_path = Path(output["output_path"])
                if not output_path.is_file():
                    raise ValidationError(f"Generated output file does not exist: {output_path}")

                source_sample = None
                if output.get("source_sample_id"):
                    source_sample = session.query(Sample).filter(Sample.id == output.get("source_sample_id")).first()
                source_labels = list(source_sample.labels_json or []) if source_sample is not None else []
                inherited_labels, label_policy = self._resolve_output_labels(output, source_labels)
                inherited_metadata = dict(output.get("metadata", {}) or {})
                inherited_metadata["label_policy"] = label_policy
                if label_policy == "inherit" and inherited_labels:
                    inherited_metadata.setdefault("labels_inherited", True)
                    inherited_metadata.setdefault("source_labels", inherited_labels)
                elif label_policy == "transformed":
                    inherited_metadata.setdefault("labels_transformed", True)
                elif label_policy == "drop":
                    inherited_metadata.setdefault("labels_dropped", True)

                generated_group_id = ""
                if target_dataset.modality == "multimodal" and source_sample is not None and sample_role(source_sample) == "image":
                    source_group_id = sample_group_id(source_sample)
                    generated_group_id = f"{source_group_id}__generated_{task_id}_{len(persisted_items):06d}"
                    inherited_metadata.update(
                        {
                            "multimodal_group_id": generated_group_id,
                            "multimodal_role": "image",
                            "source_multimodal_group_id": source_group_id,
                        }
                    )

                requested_relative_path = output.get("relative_path") or output_path.name
                if generated_group_id:
                    requested_relative_path = (Path("groups") / generated_group_id / "image" / Path(requested_relative_path).name).as_posix()
                generated_root = Path(target_dataset.storage_path) / "generated"
                copied = self.file_indexer.copy_into_dataset(output_path, generated_root, requested_relative_path)
                final_relative_path = copied.relative_to(generated_root).as_posix()
                output_sample = self.dataset_repository.create_sample(
                    session,
                    dataset_id=target_dataset.id,
                    source_sample_id=output.get("source_sample_id"),
                    name=copied.name,
                    modality=target_dataset.modality,
                    file_path=str(copied),
                    relative_path=final_relative_path,
                    sha256=self.file_indexer.compute_sha256(copied),
                    mime_type=self.file_indexer.detect_mime_type(copied),
                    extension=copied.suffix.lower(),
                    size_bytes=copied.stat().st_size,
                    status="generated",
                    metadata_json=inherited_metadata,
                    labels_json=inherited_labels or [],
                )
                row = GenerationOutput(
                    task_id=task_id,
                    source_sample_id=output.get("source_sample_id"),
                    output_sample_id=output_sample.id,
                    algorithm_id=algorithm_id,
                    status=output.get("status", "created"),
                    metadata_json=inherited_metadata,
                )
                session.add(row)
                session.flush()
                if generated_group_id and source_sample is not None:
                    self._copy_multimodal_companions(
                        session=session,
                        source_sample=source_sample,
                        target_dataset=target_dataset,
                        generated_root=generated_root,
                        generated_group_id=generated_group_id,
                        indexes=multimodal_indexes,
                    )
                persisted_items.append(self._serialize_generation_output(session, row))

            self._refresh_dataset_stats(session, target_dataset)
            self.task_repository.add_task_log(
                session,
                task_id=task_id,
                level="info",
                message="Generation outputs persisted",
                payload_json={"generated_count": len(persisted_items), "target_dataset_id": target_dataset.id},
            )
            session.commit()
        return persisted_items

    def _copy_multimodal_companions(
        self,
        *,
        session,
        source_sample: Sample,
        target_dataset: Dataset,
        generated_root: Path,
        generated_group_id: str,
        indexes: dict[int, dict[str, list[Sample]]],
    ) -> None:
        source_dataset_id = source_sample.dataset_id
        if source_dataset_id not in indexes:
            grouped: dict[str, list[Sample]] = {}
            source_samples = (
                session.query(Sample)
                .filter(Sample.dataset_id == source_dataset_id, Sample.status != "deleted")
                .all()
            )
            for sample in source_samples:
                grouped.setdefault(sample_group_id(sample), []).append(sample)
            indexes[source_dataset_id] = grouped

        for companion in indexes[source_dataset_id].get(sample_group_id(source_sample), []):
            role = sample_role(companion)
            if companion.id == source_sample.id or role == "image":
                continue
            companion_path = Path(companion.file_path or "")
            if not companion_path.is_file():
                continue
            relative_path = (
                Path("groups") / generated_group_id / role / companion_path.name
            ).as_posix()
            copied = self.file_indexer.copy_into_dataset(companion_path, generated_root, relative_path)
            metadata = sample_metadata(companion)
            metadata.update(
                {
                    "multimodal_group_id": generated_group_id,
                    "multimodal_role": role,
                    "source_multimodal_group_id": sample_group_id(source_sample),
                    "companion_copied": True,
                }
            )
            self.dataset_repository.create_sample(
                session,
                dataset_id=target_dataset.id,
                source_sample_id=companion.id,
                name=copied.name,
                modality=target_dataset.modality,
                file_path=str(copied),
                relative_path=copied.relative_to(generated_root).as_posix(),
                sha256=self.file_indexer.compute_sha256(copied),
                mime_type=self.file_indexer.detect_mime_type(copied),
                extension=copied.suffix.lower(),
                size_bytes=copied.stat().st_size,
                status="generated",
                metadata_json=metadata,
                labels_json=list(companion.labels_json or []),
            )

    def _persist_source_outputs(self, *, task_id: int, target_dataset_id: int, source_samples: list[Sample]) -> int:
        if not source_samples:
            return 0

        copied_count = 0
        with self.session_factory() as session:
            target_dataset = session.query(Dataset).filter(Dataset.id == target_dataset_id).first()
            if target_dataset is None:
                raise NotFoundError(f"Dataset {target_dataset_id} not found.")

            generated_root = Path(target_dataset.storage_path) / "generated"
            for source_sample in source_samples:
                source_path = Path(source_sample.file_path or "")
                if not source_path.is_file():
                    continue

                labels = list(source_sample.labels_json or [])
                metadata = dict(source_sample.metadata_json or {})
                metadata.update(
                    {
                        "result_type": "source",
                        "is_original": True,
                        "source_sample_id": source_sample.id,
                    }
                )
                requested_relative_path = Path("source") / (source_sample.relative_path or source_path.name)
                copied = self.file_indexer.copy_into_dataset(source_path, generated_root, requested_relative_path.as_posix())
                final_relative_path = copied.relative_to(generated_root).as_posix()
                output_sample = self.dataset_repository.create_sample(
                    session,
                    dataset_id=target_dataset.id,
                    source_sample_id=source_sample.id,
                    name=copied.name,
                    modality=target_dataset.modality,
                    file_path=str(copied),
                    relative_path=final_relative_path,
                    sha256=self.file_indexer.compute_sha256(copied),
                    mime_type=self.file_indexer.detect_mime_type(copied),
                    extension=copied.suffix.lower(),
                    size_bytes=copied.stat().st_size,
                    status="generated",
                    metadata_json=metadata,
                    labels_json=labels,
                )
                session.add(
                    GenerationOutput(
                        task_id=task_id,
                        source_sample_id=source_sample.id,
                        output_sample_id=output_sample.id,
                        algorithm_id=None,
                        status="source",
                        metadata_json=metadata,
                    )
                )
                copied_count += 1

            self._refresh_dataset_stats(session, target_dataset)
            self.task_repository.add_task_log(
                session,
                task_id=task_id,
                level="info",
                message="Source samples copied into generation outputs",
                payload_json={"source_copied_count": copied_count, "target_dataset_id": target_dataset.id},
            )
            session.commit()
        return copied_count

    def _refresh_dataset_stats(self, session, dataset: Dataset) -> None:
        total_samples = self.dataset_repository.dataset_sample_count(session, dataset.id)
        size_bytes = self.dataset_repository.dataset_total_size(session, dataset.id)
        modality_breakdown = self.dataset_repository.dataset_modality_breakdown(session, dataset.id)
        self.dataset_repository.update_dataset_counts(dataset, total_samples=total_samples, size_bytes=size_bytes)
        self.dataset_repository.upsert_statistics(
            session,
            dataset.id,
            total_samples=total_samples,
            size_bytes=size_bytes,
            modality_breakdown=modality_breakdown,
        )

    def _resolve_output_labels(self, output: dict, source_labels) -> tuple[list, str]:
        policy_value = output.get("label_policy")
        if policy_value is None:
            policy = "transformed" if "labels" in output else "inherit"
        else:
            policy = str(policy_value).strip().lower()

        if policy == "inherit":
            labels = output.get("labels")
            return list(source_labels or []) if labels is None else list(labels or []), policy
        if policy == "transformed":
            if "labels" not in output or output.get("labels") is None:
                raise ValidationError("增强插件声明已变换标签，但没有返回 labels。")
            return list(output.get("labels") or []), policy
        if policy == "drop":
            return [], policy
        if policy == "unsupported":
            if has_detection_labels(source_labels):
                raise ValidationError("该增强会改变目标位置，但暂不支持检测框变换。")
            return list(source_labels or []), "inherit"
        raise ValidationError(f"未知的标签处理策略：{policy_value}")

    def _serialize_sample(self, sample: Sample) -> dict:
        return {
            "id": sample.id,
            "name": sample.name,
            "path": sample.file_path,
            "sample_path": sample.file_path,
            "sample_type": sample.modality,
            "relative_path": sample.relative_path,
            "metadata": sample.metadata_json,
            "labels": sample.labels_json or [],
            "source_sample_id": sample.source_sample_id,
            "status": sample.status,
        }

    def _is_generation_input_sample(self, sample: Sample, modality: str) -> bool:
        path = Path(sample.file_path or "")
        if not path.is_file():
            return False
        if modality != "image":
            return True
        image_extensions = {".bmp", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}
        return path.suffix.lower() in image_extensions

    def _algorithm_matches_dataset(self, algorithm_modality: str, dataset_modality: str, generation_mode: str) -> bool:
        if algorithm_modality in {dataset_modality, "multimodal"}:
            return True
        return (
            generation_mode == "independent"
            and dataset_modality == "multimodal"
            and algorithm_modality == "image"
        )

    def _samples_for_algorithm(self, samples: list[Sample], dataset_modality: str, algorithm_modality: str) -> list[Sample]:
        if dataset_modality != "multimodal" or algorithm_modality != "image":
            return samples
        return [sample for sample in samples if sample_role(sample) == "image"]

    def _unsafe_for_multimodal_companions(self, algorithm_key: str, dataset_modality: str) -> bool:
        if dataset_modality != "multimodal":
            return False
        return algorithm_key in {
            "generation.image.crop",
            "generation.image.geometric_transform",
            "generation.image.deformation_distortion",
            "agl.image.geometric",
            "agl.image.deformation",
        }

    def _supports_pipeline(self, algorithm: Algorithm, modality: str) -> bool:
        input_contract = algorithm.input_contract_json or {}
        output_contract = algorithm.output_contract_json or {}
        if input_contract.get("supports_pipeline") is False or output_contract.get("supports_pipeline") is False:
            return False
        if input_contract.get("supports_pipeline") is True or output_contract.get("supports_pipeline") is True:
            return True
        if modality != "image" or algorithm.modality not in {"image", "multimodal"}:
            return False
        artifact_types = set(output_contract.get("artifact_types") or [])
        produces = set(output_contract.get("produces") or [])
        standalone_tokens = ("gan", "diffusion", "wgan", "mae", "vit")
        if any(token in (algorithm.key or "").lower() for token in standalone_tokens):
            return False
        return "image" in artifact_types or "generated_samples" in produces or "outputs" in produces

    def _serialize_generation_output(self, session, row: GenerationOutput) -> dict:
        source_sample_id = row.source_sample_id
        source_sample = session.query(Sample).filter(Sample.id == source_sample_id).first()
        if source_sample is None:
            # 兼容旧版插件未写入 source_sample_id 的历史生成记录。
            original_path = (row.metadata_json or {}).get("original")
            if original_path:
                source_sample = session.query(Sample).filter(Sample.file_path == str(original_path)).first()
                if source_sample is not None:
                    source_sample_id = source_sample.id
        output_sample = session.query(Sample).filter(Sample.id == row.output_sample_id).first()
        return {
            "id": row.id,
            "task_id": row.task_id,
            "source_sample_id": source_sample_id,
            "output_sample_id": row.output_sample_id,
            "algorithm_id": row.algorithm_id,
            "status": row.status,
            "metadata": row.metadata_json,
            "output_path": output_sample.file_path if output_sample else "",
            "source_sample": self._serialize_sample(source_sample) if source_sample else None,
            "output_sample": self._serialize_sample(output_sample) if output_sample else None,
        }

    def _allocate_dataset_dir(self, dataset_id: int, name: str) -> Path:
        root = self.paths.datasets_dir / f"{dataset_id}_{self._sanitize_name(name)}"
        for subdir in [root, root / "raw", root / "cleaned", root / "generated", root / "preview"]:
            subdir.mkdir(parents=True, exist_ok=True)
        return root

    def _sanitize_name(self, name: str) -> str:
        invalid = '<>:"/\\|?*'
        sanitized = "".join("_" if char in invalid else char for char in name).strip().strip(".")
        return sanitized or "dataset"
