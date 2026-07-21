from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from backend.database import Base, create_backend_engine, create_session_factory
from backend.models import Dataset, GenerationOutput, Sample, Task
from backend.repositories.dataset_repository import DatasetRepository
from backend.repositories.task_repository import TaskRepository
from backend.services.generation_service import GenerationService
from backend.storage import FileIndexer


class _ProgressRecorder:
    def __init__(self):
        self.updates = []

    def set_progress(self, task_id, progress, message):
        self.updates.append((task_id, progress, message))


class _NoRehashFileIndexer(FileIndexer):
    def compute_sha256(self, file_path):
        raise AssertionError("source copies must reuse the existing SHA256")


class GenerationServicePersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.engine = create_backend_engine(self.root / "test.db")
        Base.metadata.create_all(self.engine)
        self.session_factory = create_session_factory(self.engine)
        self.dataset_repository = DatasetRepository(self.session_factory)
        self.task_repository = TaskRepository(self.session_factory)
        self.progress = _ProgressRecorder()
        self.service = GenerationService(
            paths=SimpleNamespace(datasets_dir=self.root / "datasets"),
            session_factory=self.session_factory,
            task_manager=self.progress,
            task_repository=self.task_repository,
            algorithm_repository=None,
            dataset_repository=self.dataset_repository,
            file_indexer=_NoRehashFileIndexer(),
        )

    def tearDown(self):
        self.engine.dispose()
        self.temp_dir.cleanup()

    def test_source_outputs_are_batched_and_reuse_source_metadata(self):
        source_root = self.root / "source"
        target_root = self.root / "target"
        source_root.mkdir()
        target_root.mkdir()

        with self.session_factory() as session:
            source_dataset = Dataset(name="source", modality="image", storage_path=str(source_root))
            target_dataset = Dataset(name="target", modality="image", storage_path=str(target_root))
            session.add_all([source_dataset, target_dataset])
            session.flush()
            task = Task(
                task_type="generation",
                status="running",
                title="test",
                source_dataset_id=source_dataset.id,
                target_dataset_id=target_dataset.id,
            )
            session.add(task)
            session.flush()
            for index in range(3):
                source_path = source_root / f"sample_{index}.jpg"
                source_path.write_bytes(f"sample-{index}".encode())
                session.add(
                    Sample(
                        dataset_id=source_dataset.id,
                        name=source_path.name,
                        modality="image",
                        file_path=str(source_path),
                        relative_path=source_path.name,
                        sha256=f"sha-{index}",
                        mime_type="image/jpeg",
                        extension=".jpg",
                        size_bytes=source_path.stat().st_size,
                        labels_json=[{"type": "classification", "class_name": "ship"}],
                    )
                )
            session.commit()
            task_id = task.id
            source_dataset_id = source_dataset.id
            target_dataset_id = target_dataset.id

        with self.session_factory() as session:
            source_samples = session.query(Sample).filter(Sample.dataset_id == source_dataset_id).all()

        with patch("backend.services.generation_service.SOURCE_OUTPUT_BATCH_SIZE", 2):
            copied_count = self.service._persist_source_outputs(
                task_id=task_id,
                target_dataset_id=target_dataset_id,
                source_samples=source_samples,
            )

        self.assertEqual(copied_count, 3)
        self.assertEqual([(item[0], item[1]) for item in self.progress.updates], [(task_id, 99.0)])
        with self.session_factory() as session:
            copied_samples = (
                session.query(Sample)
                .filter(Sample.dataset_id == target_dataset_id)
                .order_by(Sample.id)
                .all()
            )
            outputs = session.query(GenerationOutput).filter(GenerationOutput.task_id == task_id).all()
            persisted_task = session.query(Task).filter(Task.id == task_id).one()

            self.assertEqual([sample.sha256 for sample in copied_samples], ["sha-0", "sha-1", "sha-2"])
            self.assertEqual(len(outputs), 3)
            self.assertEqual(persisted_task.progress, 99.9)
            self.assertTrue(persisted_task.progress_message.endswith("3/3"))
            self.assertTrue(all(Path(sample.file_path).is_file() for sample in copied_samples))

    def test_staged_generation_dataset_is_hidden_until_stored(self):
        source_root = self.root / "source_visible"
        source_root.mkdir()

        with self.session_factory() as session:
            source_dataset = Dataset(
                name="source",
                modality="image",
                status="raw",
                storage_path=str(source_root),
            )
            session.add(source_dataset)
            session.flush()
            target_dataset = self.service._resolve_target_dataset(session, source_dataset, 0)
            task = Task(
                task_type="generation",
                status="completed",
                title="store test",
                source_dataset_id=source_dataset.id,
                target_dataset_id=target_dataset.id,
                result_json={"generated_count": 1},
            )
            session.add(task)
            session.commit()
            source_dataset_id = source_dataset.id
            target_dataset_id = target_dataset.id
            task_id = task.id

        with self.session_factory() as session:
            _, visible_before = self.dataset_repository.list_datasets(session, page=1, page_size=None)
            self.assertEqual([dataset.id for dataset in visible_before], [source_dataset_id])
            self.assertEqual(self.dataset_repository.count_active_datasets(session), 1)

        result = self.service.store_generated_dataset(task_id, "source_generated")

        self.assertTrue(result["ok"])
        with self.session_factory() as session:
            _, visible_after = self.dataset_repository.list_datasets(session, page=1, page_size=None)
            self.assertEqual(
                {dataset.id for dataset in visible_after},
                {source_dataset_id, target_dataset_id},
            )
            self.assertEqual(self.dataset_repository.count_active_datasets(session), 2)
            stored = session.query(Dataset).filter(Dataset.id == target_dataset_id).one()
            persisted_task = session.query(Task).filter(Task.id == task_id).one()
            self.assertEqual(stored.name, "source_generated")
            self.assertEqual(stored.status, "generated")
            self.assertEqual(stored.tags_json, ["generated"])
            self.assertEqual(persisted_task.result_json["stored_dataset_id"], target_dataset_id)


if __name__ == "__main__":
    unittest.main()
