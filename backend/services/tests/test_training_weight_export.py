from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from backend.database import Base, create_backend_engine, create_session_factory
from backend.models import Task
from backend.qt.bridge import BackendBridge
from backend.repositories.task_repository import TaskRepository


class TrainingWeightExportTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.engine = create_backend_engine(self.root / "test.db")
        Base.metadata.create_all(self.engine)
        self.session_factory = create_session_factory(self.engine)
        self.task_repository = TaskRepository(self.session_factory)
        self.bridge = BackendBridge(
            facade=SimpleNamespace(
                session_factory=self.session_factory,
                task_repository=self.task_repository,
            )
        )

    def tearDown(self):
        self.engine.dispose()
        self.temp_dir.cleanup()

    def test_exports_weights_under_selected_directory(self):
        artifact = self.root / "best.pt"
        artifact.write_bytes(b"weights")
        selected_dir = self.root / "selected"
        selected_dir.mkdir()

        with self.session_factory() as session:
            task = Task(
                task_type="training",
                status="completed",
                title="training",
                result_json={"artifacts": [str(artifact)]},
            )
            session.add(task)
            session.commit()
            task_id = task.id

        result = self.bridge.export_training_weights(task_id, "test model", str(selected_dir))

        self.assertTrue(result["ok"])
        export_dir = Path(result["path"])
        self.assertEqual(export_dir.parent, selected_dir)
        self.assertEqual([path.name for path in export_dir.iterdir()], ["best.pt"])

    def test_rejects_missing_export_directory(self):
        result = self.bridge.export_training_weights(1, "test", str(self.root / "missing"))

        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "VALIDATION_ERROR")


if __name__ == "__main__":
    unittest.main()
