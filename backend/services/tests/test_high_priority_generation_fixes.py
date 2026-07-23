from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from backend.database import Base, create_backend_engine, create_session_factory
from backend.errors import ValidationError
from backend.models import Algorithm, AlgorithmParameter, Dataset, Sample, Task
from backend.qt.bridge import BackendBridge
from backend.repositories.algorithm_repository import AlgorithmRepository
from backend.repositories.dataset_repository import DatasetRepository
from backend.repositories.log_repository import LogRepository
from backend.repositories.task_repository import TaskRepository
from backend.services.algorithm_service import AlgorithmService
from backend.services.generation_service import GenerationService, _GenerationCancelled
from backend.storage import FileIndexer
from backend.task_manager import TaskManager


class _ProgressRecorder:
    def set_progress(self, *_args):
        pass


class _ForbiddenProgressRecorder:
    def set_progress(self, *_args):
        raise AssertionError("合并原图时不应通过独立会话更新进度")


class _CancelAfterFirstCopy:
    def __init__(self):
        self.calls = 0

    def is_cancel_requested(self):
        self.calls += 1
        return self.calls >= 2


class _EmptyRunner:
    def run(self, *_args, **_kwargs):
        return {"ok": True, "outputs": [], "logs": []}


class HighPriorityGenerationFixTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.engine = create_backend_engine(self.root / "test.db")
        Base.metadata.create_all(self.engine)
        self.session_factory = create_session_factory(self.engine)
        self.dataset_repository = DatasetRepository(self.session_factory)
        self.task_repository = TaskRepository(self.session_factory)

    def tearDown(self):
        self.engine.dispose()
        self.temp_dir.cleanup()

    def test_atomic_persistence_rolls_back_rows_and_copied_files(self):
        source_file = self.root / "plugin-output.jpg"
        source_file.write_bytes(b"generated")
        target_dir = self.root / "target"
        target_dir.mkdir()

        with self.session_factory() as session:
            target = Dataset(name="target", modality="image", status="staging", storage_path=str(target_dir))
            session.add(target)
            session.flush()
            task = Task(task_type="generation", status="running", title="test", target_dataset_id=target.id)
            session.add(task)
            session.commit()
            task_id = task.id
            target_id = target.id

        service = GenerationService(
            paths=SimpleNamespace(datasets_dir=self.root),
            session_factory=self.session_factory,
            task_manager=_ProgressRecorder(),
            task_repository=self.task_repository,
            algorithm_repository=None,
            dataset_repository=self.dataset_repository,
            file_indexer=FileIndexer(),
        )
        outputs = [
            {"output_path": str(source_file), "relative_path": "first.jpg"},
            {"output_path": str(self.root / "missing.jpg"), "relative_path": "second.jpg"},
        ]

        with self.assertRaises(ValidationError):
            service._persist_task_outputs_transaction(
                task_id=task_id,
                target_dataset_id=target_id,
                outputs_by_algorithm=[(1, outputs)],
                source_samples=[],
                plugin_context=None,
            )

        with self.session_factory() as session:
            self.assertEqual(session.query(Sample).filter(Sample.dataset_id == target_id).count(), 0)
        self.assertEqual(list((target_dir / "generated").glob("**/*.*")), [])

    def test_source_merge_updates_progress_in_persistence_session(self):
        source_dir = self.root / "source-progress"
        target_dir = self.root / "target-progress"
        source_dir.mkdir()
        target_dir.mkdir()
        source_file = source_dir / "source.jpg"
        generated_file = self.root / "generated.jpg"
        source_file.write_bytes(b"source")
        generated_file.write_bytes(b"generated")

        with self.session_factory() as session:
            source_dataset = Dataset(name="source", modality="image", status="raw", storage_path=str(source_dir))
            target = Dataset(name="target", modality="image", status="staging", storage_path=str(target_dir))
            session.add_all([source_dataset, target])
            session.flush()
            source_sample = Sample(
                dataset_id=source_dataset.id,
                name=source_file.name,
                modality="image",
                file_path=str(source_file),
                relative_path=source_file.name,
                size_bytes=source_file.stat().st_size,
            )
            session.add(source_sample)
            session.flush()
            task = Task(task_type="generation", status="running", title="test", target_dataset_id=target.id)
            session.add(task)
            session.commit()
            task_id = task.id
            target_id = target.id
            source_sample_id = source_sample.id

        with self.session_factory() as session:
            source_samples = session.query(Sample).filter(Sample.id == source_sample_id).all()

        service = GenerationService(
            paths=SimpleNamespace(datasets_dir=self.root),
            session_factory=self.session_factory,
            task_manager=_ForbiddenProgressRecorder(),
            task_repository=self.task_repository,
            algorithm_repository=None,
            dataset_repository=self.dataset_repository,
            file_indexer=FileIndexer(),
        )
        service._persist_task_outputs_transaction(
            task_id=task_id,
            target_dataset_id=target_id,
            outputs_by_algorithm=[
                (1, [{"output_path": str(generated_file), "source_sample_id": source_sample_id}])
            ],
            source_samples=source_samples,
            plugin_context=None,
        )

        with self.session_factory() as session:
            task = session.query(Task).filter(Task.id == task_id).one()
            self.assertEqual(task.progress_message, "正在合并原始样本 1/1")
            self.assertEqual(session.query(Sample).filter(Sample.dataset_id == target_id).count(), 2)


    def test_cancelling_pending_generation_discards_staging_dataset(self):
        target_dir = self.root / "staging"
        target_dir.mkdir()
        (target_dir / "placeholder.txt").write_text("x", encoding="utf-8")
        with self.session_factory() as session:
            target = Dataset(
                name="target",
                modality="image",
                status="staging",
                storage_path=str(target_dir),
                tags_json=["generation_staging"],
                extra_json={"dataset_stage": "staging"},
            )
            session.add(target)
            session.flush()
            task = Task(task_type="generation", status="pending", title="test", target_dataset_id=target.id)
            session.add(task)
            session.commit()
            task_id = task.id
            target_id = target.id

        manager = TaskManager(
            paths=SimpleNamespace(),
            session_factory=self.session_factory,
            task_repository=self.task_repository,
            log_repository=None,
        )
        manager.cancel(task_id)

        with self.session_factory() as session:
            task = session.query(Task).filter(Task.id == task_id).one()
            target = session.query(Dataset).filter(Dataset.id == target_id).one()
            self.assertEqual(task.status, "cancelled")
            self.assertEqual(target.status, "deleted")
            self.assertEqual(target.storage_path, "")
        self.assertFalse(target_dir.exists())

    def test_running_task_cannot_be_deleted(self):
        with self.session_factory() as session:
            task = Task(task_type="generation", status="running", title="running")
            session.add(task)
            session.commit()
            task_id = task.id

        with self.session_factory() as session:
            with self.assertRaises(ValidationError):
                self.task_repository.delete_task(session, task_id)

        with self.session_factory() as session:
            self.assertIsNotNone(session.query(Task).filter(Task.id == task_id).first())

    def test_cancellation_during_source_copy_rolls_back_everything(self):
        source_dir = self.root / "source"
        source_dir.mkdir()
        target_dir = self.root / "target-cancel"
        target_dir.mkdir()
        with self.session_factory() as session:
            source_dataset = Dataset(name="source", modality="image", status="raw", storage_path=str(source_dir))
            target = Dataset(name="target", modality="image", status="staging", storage_path=str(target_dir))
            session.add_all([source_dataset, target])
            session.flush()
            for index in range(2):
                path = source_dir / f"{index}.jpg"
                path.write_bytes(f"source-{index}".encode())
                session.add(
                    Sample(
                        dataset_id=source_dataset.id,
                        name=path.name,
                        modality="image",
                        file_path=str(path),
                        relative_path=path.name,
                        size_bytes=path.stat().st_size,
                    )
                )
            task = Task(task_type="generation", status="running", title="test", target_dataset_id=target.id)
            session.add(task)
            session.commit()
            task_id = task.id
            target_id = target.id

        with self.session_factory() as session:
            source_samples = session.query(Sample).order_by(Sample.id).all()

        service = GenerationService(
            paths=SimpleNamespace(datasets_dir=self.root),
            session_factory=self.session_factory,
            task_manager=_ProgressRecorder(),
            task_repository=self.task_repository,
            algorithm_repository=None,
            dataset_repository=self.dataset_repository,
            file_indexer=FileIndexer(),
        )
        with self.assertRaises(_GenerationCancelled):
            service._persist_task_outputs_transaction(
                task_id=task_id,
                target_dataset_id=target_id,
                outputs_by_algorithm=[],
                source_samples=source_samples,
                plugin_context=_CancelAfterFirstCopy(),
            )

        with self.session_factory() as session:
            self.assertEqual(session.query(Sample).filter(Sample.dataset_id == target_id).count(), 0)
        self.assertEqual(list((target_dir / "generated").glob("**/*.*")), [])

    def test_zero_plugin_outputs_fail_task_and_discard_staging(self):
        source_dir = self.root / "run-source"
        source_dir.mkdir()
        source_file = source_dir / "source.jpg"
        source_file.write_bytes(b"source")
        target_dir = self.root / "run-target"
        target_dir.mkdir()
        output_dir = self.root / "task-output"
        output_dir.mkdir()
        with self.session_factory() as session:
            source_dataset = Dataset(name="source", modality="image", status="raw", storage_path=str(source_dir))
            target = Dataset(
                name="target",
                modality="image",
                status="staging",
                storage_path=str(target_dir),
                tags_json=["generation_staging"],
                extra_json={"dataset_stage": "staging"},
            )
            algorithm = Algorithm(
                key="generation.empty",
                name="empty",
                category="generation",
                modality="image",
                status="enabled",
                entry_type="python",
                module_path="unused",
                callable_name="run",
            )
            session.add_all([source_dataset, target, algorithm])
            session.flush()
            session.add(
                Sample(
                    dataset_id=source_dataset.id,
                    name=source_file.name,
                    modality="image",
                    file_path=str(source_file),
                    relative_path=source_file.name,
                    size_bytes=source_file.stat().st_size,
                )
            )
            task = Task(
                task_type="generation",
                status="running",
                title="empty",
                source_dataset_id=source_dataset.id,
                target_dataset_id=target.id,
                algorithm_id=algorithm.id,
                parameters_json={"algorithm_parameters": {str(algorithm.id): {}}},
                payload_json={
                    "algorithm_ids": [algorithm.id],
                    "target_count": 1,
                    "generation_mode": "independent",
                },
                output_dir=str(output_dir),
            )
            session.add(task)
            session.commit()
            task_id = task.id
            target_id = target.id

        manager = TaskManager(
            paths=SimpleNamespace(tasks_dir=self.root / "tasks"),
            session_factory=self.session_factory,
            task_repository=self.task_repository,
            log_repository=LogRepository(self.session_factory),
        )
        service = GenerationService(
            paths=SimpleNamespace(datasets_dir=self.root / "datasets"),
            session_factory=self.session_factory,
            task_manager=manager,
            task_repository=self.task_repository,
            algorithm_repository=AlgorithmRepository(self.session_factory),
            dataset_repository=self.dataset_repository,
            plugin_runner=_EmptyRunner(),
            file_indexer=FileIndexer(),
        )

        result = service.run_task(task_id)

        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "INSUFFICIENT_OUTPUTS")
        with self.session_factory() as session:
            task = session.query(Task).filter(Task.id == task_id).one()
            target = session.query(Dataset).filter(Dataset.id == target_id).one()
            self.assertEqual(task.status, "failed")
            self.assertEqual(target.status, "deleted")
        self.assertFalse(target_dir.exists())

    def test_plugin_import_uses_unique_name_instead_of_overwriting(self):
        plugins_dir = self.root / "plugins"
        user_dir = plugins_dir / "user"
        user_dir.mkdir(parents=True)
        existing = user_dir / "plugin.py"
        existing.write_text("VALUE = 'old'\n", encoding="utf-8")
        source_dir = self.root / "incoming"
        source_dir.mkdir()
        source = source_dir / "plugin.py"
        source.write_text("VALUE = 'new'\n", encoding="utf-8")
        bridge = BackendBridge(facade=SimpleNamespace(paths=SimpleNamespace(plugins_dir=plugins_dir)))

        result = bridge.import_plugin_file(str(source))

        self.assertTrue(result["ok"])
        self.assertEqual(existing.read_text(encoding="utf-8"), "VALUE = 'old'\n")
        imported = Path(result["path"])
        self.assertEqual(imported.name, "plugin_1.py")
        self.assertEqual(imported.read_text(encoding="utf-8"), "VALUE = 'new'\n")

    def test_algorithm_delete_clears_parameters_and_historical_references(self):
        with self.session_factory() as session:
            algorithm = Algorithm(
                key="generation.test",
                name="test",
                category="generation",
                modality="image",
                entry_type="python",
            )
            session.add(algorithm)
            session.flush()
            algorithm_id = algorithm.id
            session.add(AlgorithmParameter(algorithm_id=algorithm_id, name="x", label="x", type="int"))
            session.add(
                Task(
                    task_type="generation",
                    status="completed",
                    title="history",
                    algorithm_id=algorithm_id,
                    parameters_json={
                        "algorithm_ids": [algorithm_id],
                        "algorithm_parameters": {str(algorithm_id): {"x": 1}},
                    },
                    payload_json={"algorithm_ids": [algorithm_id]},
                )
            )
            session.commit()

        service = AlgorithmService(
            paths=SimpleNamespace(),
            session_factory=self.session_factory,
            algorithm_repository=AlgorithmRepository(self.session_factory),
            log_repository=LogRepository(self.session_factory),
        )
        service.delete_algorithm(algorithm_id)

        with self.session_factory() as session:
            self.assertIsNone(session.query(Algorithm).filter(Algorithm.id == algorithm_id).first())
            self.assertEqual(session.query(AlgorithmParameter).filter_by(algorithm_id=algorithm_id).count(), 0)
            task = session.query(Task).filter(Task.title == "history").one()
            self.assertIsNone(task.algorithm_id)
            self.assertEqual(task.parameters_json["algorithm_ids"], [])
            self.assertEqual(task.parameters_json["algorithm_parameters"], {})
            self.assertEqual(task.payload_json["algorithm_ids"], [])

    def test_algorithm_delete_rejects_active_task(self):
        with self.session_factory() as session:
            algorithm = Algorithm(
                key="generation.active",
                name="active",
                category="generation",
                modality="image",
                entry_type="python",
            )
            session.add(algorithm)
            session.flush()
            algorithm_id = algorithm.id
            session.add(
                Task(
                    task_type="generation",
                    status="running",
                    title="active",
                    parameters_json={"algorithm_ids": [algorithm_id]},
                    payload_json={"algorithm_ids": [algorithm_id]},
                )
            )
            session.commit()

        service = AlgorithmService(
            paths=SimpleNamespace(),
            session_factory=self.session_factory,
            algorithm_repository=AlgorithmRepository(self.session_factory),
            log_repository=LogRepository(self.session_factory),
        )
        with self.assertRaises(ValidationError):
            service.delete_algorithm(algorithm_id)
