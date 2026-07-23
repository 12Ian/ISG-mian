from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import event

from backend.database import Base, create_backend_engine, create_session_factory
from backend.errors import ValidationError
from backend.models import Algorithm, Dataset, GenerationOutput, Sample, Task
from backend.parameter_ranges import normalize_parameter_sampling_value
from backend.plugins.reflector import validate_parameters
from backend.plugins.runner import PluginRunner
from backend.repositories.algorithm_repository import AlgorithmRepository
from backend.repositories.dataset_repository import DatasetRepository
from backend.repositories.task_repository import TaskRepository
from backend.services.generation_service import GenerationService
from backend.storage import FileIndexer


class MediumPriorityGenerationFixTests(unittest.TestCase):
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

    def _generation_service(self, **overrides):
        values = {
            "paths": SimpleNamespace(datasets_dir=self.root / "datasets"),
            "session_factory": self.session_factory,
            "task_manager": None,
            "task_repository": self.task_repository,
            "algorithm_repository": AlgorithmRepository(self.session_factory),
            "dataset_repository": self.dataset_repository,
            "file_indexer": FileIndexer(),
        }
        values.update(overrides)
        return GenerationService(**values)

    def test_fractional_integer_bounds_are_never_crossed(self):
        parameter = {
            "name": "count",
            "type": "int",
            "default_value": 3,
            "min_value": 1.2,
            "max_value": 5.8,
        }
        self.assertEqual(
            normalize_parameter_sampling_value(parameter, {"min": -10, "max": 20}),
            {"min": 2, "max": 5},
        )

    def test_parameter_contract_rejects_ambiguous_definitions(self):
        valid, error = validate_parameters(
            [
                {"name": "x", "type": "int", "default": 2, "min": 0, "max": 3},
                {"name": "x", "type": "float", "default": 0.5, "min": 0.0, "max": 1.0},
            ]
        )
        self.assertFalse(valid)
        self.assertIn("重复", error)

        invalid_contracts = [
            [{"name": "", "type": "int", "default": 1}],
            [{"name": "x", "type": "int", "default": 1.5, "min": 0, "max": 2}],
            [{"name": "x", "type": "float", "default": 2.0, "min": 0.0, "max": 1.0}],
            [{"name": "x", "type": "float", "default": 0.5, "min": 1.0, "max": 0.0}],
            [{"name": "x", "type": "select", "default": "c", "options": ["a", "b"]}],
        ]
        for contract in invalid_contracts:
            self.assertFalse(validate_parameters(contract)[0])

    def test_script_plugin_module_is_cached_until_file_changes(self):
        script = self.root / "cached_plugin.py"
        counter = self.root / "cached_plugin.count"
        script.write_text(
            "from pathlib import Path\n"
            "counter = Path(__file__).with_suffix('.count')\n"
            "counter.write_text(counter.read_text() + 'x' if counter.exists() else 'x')\n"
            "def run(payload, context):\n"
            "    return {'ok': True, 'outputs': []}\n",
            encoding="utf-8",
        )
        runner = PluginRunner()
        config = {"script_path": str(script), "callable_name": "run"}

        runner.run({}, None, **config)
        runner.run({}, None, **config)

        self.assertEqual(counter.read_text(encoding="utf-8"), "x")

    def test_pipeline_preserves_sampled_parameters_from_every_stage(self):
        service = self._generation_service()
        source = {
            "id": 1,
            "metadata": {"pipeline_sampled_parameters": {"stage.one": {"alpha": 0.4}}},
            "pipeline_algorithms": ["stage.one"],
            "labels": [],
        }
        algorithm = SimpleNamespace(key="stage.two")
        result = service._outputs_as_pipeline_samples(
            [
                {
                    "source_sample_id": 1,
                    "output_path": str(self.root / "stage-two.jpg"),
                    "metadata": {"sampled_parameters": {"beta": 0.7}},
                }
            ],
            [source],
            algorithm,
        )

        self.assertEqual(
            result[0]["metadata"]["pipeline_sampled_parameters"],
            {"stage.one": {"alpha": 0.4}, "stage.two": {"beta": 0.7}},
        )

    def test_default_output_list_excludes_source_rows_and_avoids_n_plus_one(self):
        with self.session_factory() as session:
            dataset = Dataset(name="data", modality="image", status="generated", storage_path=str(self.root))
            session.add(dataset)
            session.flush()
            source = Sample(dataset_id=dataset.id, name="source.jpg", modality="image", file_path="source.jpg")
            generated = Sample(dataset_id=dataset.id, name="generated.jpg", modality="image", file_path="generated.jpg")
            source_copy = Sample(dataset_id=dataset.id, name="copy.jpg", modality="image", file_path="copy.jpg")
            session.add_all([source, generated, source_copy])
            session.flush()
            task = Task(task_type="generation", status="completed", title="test")
            session.add(task)
            session.flush()
            session.add_all(
                [
                    GenerationOutput(
                        task_id=task.id,
                        source_sample_id=source.id,
                        output_sample_id=generated.id,
                        status="created",
                    ),
                    GenerationOutput(
                        task_id=task.id,
                        source_sample_id=source.id,
                        output_sample_id=source_copy.id,
                        status="source",
                    ),
                ]
            )
            session.commit()
            task_id = task.id

        select_count = 0

        def count_selects(_conn, _cursor, statement, _parameters, _context, _executemany):
            nonlocal select_count
            if statement.lstrip().upper().startswith("SELECT"):
                select_count += 1

        event.listen(self.engine, "before_cursor_execute", count_selects)
        try:
            result = self._generation_service().list_outputs(task_id, None, 1, 200)
        finally:
            event.remove(self.engine, "before_cursor_execute", count_selects)

        self.assertEqual(result["total"], 1)
        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(result["items"][0]["status"], "created")
        self.assertLessEqual(select_count, 3)

    def test_history_has_no_200_item_cap_and_filters_dataset(self):
        with self.session_factory() as session:
            first = Dataset(name="first", modality="image", status="raw", storage_path="first")
            second = Dataset(name="second", modality="image", status="raw", storage_path="second")
            session.add_all([first, second])
            session.flush()
            session.add_all(
                [
                    Task(task_type="generation", status="completed", title=f"task-{index}", source_dataset_id=first.id)
                    for index in range(205)
                ]
            )
            session.add(Task(task_type="generation", status="completed", title="other", source_dataset_id=second.id))
            session.commit()
            first_id = first.id

        result = self.task_repository.list_tasks(
            task_type="generation",
            status="",
            page=1,
            page_size=None,
            dataset_id=first_id,
        )
        self.assertEqual(result["total"], 205)
        self.assertEqual(len(result["items"]), 205)

    def test_independent_mode_requires_at_least_one_output_per_algorithm(self):
        source_dir = self.root / "source"
        source_dir.mkdir()
        source_file = source_dir / "source.jpg"
        source_file.write_bytes(b"source")
        with self.session_factory() as session:
            dataset = Dataset(name="source", modality="image", status="raw", storage_path=str(source_dir))
            algorithms = [
                Algorithm(
                    key=f"generation.test.{index}",
                    name=f"algorithm-{index}",
                    category="generation",
                    modality="image",
                    status="enabled",
                    entry_type="python",
                    module_path="unused",
                    callable_name="run",
                )
                for index in range(2)
            ]
            session.add(dataset)
            session.add_all(algorithms)
            session.flush()
            session.add(
                Sample(
                    dataset_id=dataset.id,
                    name=source_file.name,
                    modality="image",
                    file_path=str(source_file),
                )
            )
            session.commit()
            dataset_id = dataset.id
            algorithm_ids = [item.id for item in algorithms]

        with self.assertRaises(ValidationError):
            self._generation_service().create_task(
                dataset_id,
                0,
                algorithm_ids,
                {"generation_mode": "independent"},
                1,
            )

