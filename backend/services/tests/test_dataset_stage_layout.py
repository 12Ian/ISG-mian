from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from backend.database import Base, create_backend_engine, create_session_factory
from backend.models import Dataset, Sample, Task
from backend.repositories.dataset_repository import DatasetRepository
from backend.repositories.log_repository import LogRepository
from backend.repositories.task_repository import TaskRepository
from backend.services.cleaning_service import CleaningService
from backend.services.dataset_layout import normalize_dataset_relative_path
from backend.services.dataset_service import DatasetService
from backend.services.generation_service import GenerationService
from backend.storage import FileIndexer


class DatasetStageLayoutTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.engine = create_backend_engine(self.root / "test.db")
        Base.metadata.create_all(self.engine)
        self.session_factory = create_session_factory(self.engine)
        self.dataset_repository = DatasetRepository(self.session_factory)
        self.task_repository = TaskRepository(self.session_factory)
        self.paths = SimpleNamespace(datasets_dir=self.root / "datasets")

    def tearDown(self):
        self.engine.dispose()
        self.temp_dir.cleanup()

    def _dataset_service(self) -> DatasetService:
        return DatasetService(
            paths=self.paths,
            session_factory=self.session_factory,
            dataset_repository=self.dataset_repository,
            log_repository=LogRepository(self.session_factory),
        )

    def test_import_flattens_stage_directories_and_reads_each_manifest(self):
        source = self.root / "exported"
        for stage in ("raw", "cleaned", "generated", "preview"):
            (source / stage).mkdir(parents=True)

        raw_image = source / "raw" / "cat" / "a.jpg"
        generated_image = source / "generated" / "dog" / "b.jpg"
        raw_image.parent.mkdir(parents=True)
        generated_image.parent.mkdir(parents=True)
        raw_image.write_bytes(b"cat")
        generated_image.write_bytes(b"dog")
        (source / "raw" / "dataset_manifest.json").write_text(
            json.dumps({"samples": {"1": {"path": "cat/a.jpg", "labels": ["cat"]}}}),
            encoding="utf-8",
        )
        (source / "generated" / "dataset_manifest.json").write_text(
            json.dumps({"samples": {"1": {"path": "dog/b.jpg", "labels": ["dog"]}}}),
            encoding="utf-8",
        )

        service = self._dataset_service()
        dataset_id = service.create_dataset("stage-import", "image")["data"]["id"]
        result = service.import_folder(dataset_id, str(source), include_subfolders=True)

        self.assertEqual(result["data"]["imported_count"], 2)
        with self.session_factory() as session:
            dataset = self.dataset_repository.get_dataset(session, dataset_id)
            samples = self.dataset_repository.get_all_samples(session, dataset_id)
            self.assertEqual(
                {sample.relative_path for sample in samples},
                {"cat/a.jpg", "dog/b.jpg"},
            )
            self.assertEqual(
                {sample.labels_json[0]["class_name"] for sample in samples},
                {"cat", "dog"},
            )
            self.assertEqual(dataset.extra_json["class_distribution"], {"cat": 1, "dog": 1})
            dataset_root = Path(dataset.storage_path)

        self.assertTrue((dataset_root / "raw" / "cat" / "a.jpg").is_file())
        self.assertTrue((dataset_root / "raw" / "dog" / "b.jpg").is_file())
        self.assertFalse((dataset_root / "raw" / "raw").exists())
        self.assertFalse((dataset_root / "raw" / "generated").exists())

    def test_normal_directory_import_keeps_class_structure(self):
        source = self.root / "normal" / "cat"
        source.mkdir(parents=True)
        (source / "a.jpg").write_bytes(b"cat")

        service = self._dataset_service()
        dataset_id = service.create_dataset("normal-import", "image")["data"]["id"]
        service.import_folder(dataset_id, str(source.parent), include_subfolders=True)

        with self.session_factory() as session:
            samples = self.dataset_repository.get_all_samples(session, dataset_id)
            self.assertEqual(samples[0].relative_path, "cat/a.jpg")
            self.assertEqual(samples[0].labels_json[0]["class_name"], "cat")

    def test_cleaning_and_generation_strip_existing_stage_prefixes(self):
        source_root = self.root / "source-dataset"
        source_file = source_root / "raw" / "cat" / "a.jpg"
        source_file.parent.mkdir(parents=True)
        source_file.write_bytes(b"source")

        with self.session_factory() as session:
            source_dataset = Dataset(
                name="source",
                modality="image",
                status="raw",
                storage_path=str(source_root),
            )
            generation_target = Dataset(
                name="generation-target",
                modality="image",
                status="staging",
                storage_path=str(self.root / "generation-target"),
            )
            session.add_all([source_dataset, generation_target])
            session.flush()
            sample = Sample(
                dataset_id=source_dataset.id,
                name=source_file.name,
                modality="image",
                file_path=str(source_file),
                relative_path="raw/cleaned/cat/a.jpg",
                sha256="source-sha",
                mime_type="image/jpeg",
                extension=".jpg",
                size_bytes=source_file.stat().st_size,
                labels_json=[{"type": "classification", "class_name": "cat"}],
            )
            session.add(sample)
            session.flush()
            cleaning_task = Task(
                task_type="cleaning",
                status="completed",
                title="cleaning",
                source_dataset_id=source_dataset.id,
                target_dataset_id=source_dataset.id,
            )
            generation_task = Task(
                task_type="generation",
                status="running",
                title="generation",
                source_dataset_id=source_dataset.id,
                target_dataset_id=generation_target.id,
            )
            session.add_all([cleaning_task, generation_task])
            session.commit()
            sample_id = sample.id
            cleaning_task_id = cleaning_task.id
            generation_task_id = generation_task.id
            generation_target_id = generation_target.id

        cleaning_service = CleaningService(
            paths=self.paths,
            session_factory=self.session_factory,
            task_manager=SimpleNamespace(),
            task_repository=self.task_repository,
            algorithm_repository=None,
            dataset_repository=self.dataset_repository,
            file_indexer=FileIndexer(),
        )
        cleaned = cleaning_service.store_cleaned_dataset(cleaning_task_id, "cleaned-target")
        cleaned_dataset_id = cleaned["data"]["dataset"]["id"]

        with self.session_factory() as session:
            source_sample = session.query(Sample).filter(Sample.id == sample_id).one()
            source_sample.relative_path = "generated/source/source/raw/cleaned/cat/a.jpg"
            source_samples = [source_sample]

        generation_service = GenerationService(
            paths=self.paths,
            session_factory=self.session_factory,
            task_manager=SimpleNamespace(),
            task_repository=self.task_repository,
            algorithm_repository=None,
            dataset_repository=self.dataset_repository,
            file_indexer=FileIndexer(),
        )
        generation_service._persist_source_outputs(
            task_id=generation_task_id,
            target_dataset_id=generation_target_id,
            source_samples=source_samples,
        )

        with self.session_factory() as session:
            cleaned_sample = session.query(Sample).filter(Sample.dataset_id == cleaned_dataset_id).one()
            generated_sample = session.query(Sample).filter(Sample.dataset_id == generation_target_id).one()
            self.assertEqual(cleaned_sample.relative_path, "cat/a.jpg")
            self.assertEqual(generated_sample.relative_path, "source/cat/a.jpg")

        self.assertEqual(normalize_dataset_relative_path("raw/cleaned/generated/cat/a.jpg"), "cat/a.jpg")
        self.assertFalse((Path(cleaned_sample.file_path).parent.parent / "raw").exists())


if __name__ == "__main__":
    unittest.main()
