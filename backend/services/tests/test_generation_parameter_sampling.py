from types import SimpleNamespace

from backend.parameter_ranges import (
    default_parameter_sampling_range,
    normalize_parameter_sampling_value,
    parameter_display_precision,
    parameter_sampling_is_variable,
    sample_parameter_value,
)
from backend.services.generation_service import GenerationService


INT_PARAMETER = {
    "name": "amount",
    "type": "int",
    "default_value": 5,
    "min_value": 0,
    "max_value": 10,
    "options": [],
}


def test_default_sampling_range_uses_about_one_third_of_allowed_range():
    assert default_parameter_sampling_range(INT_PARAMETER) == {"min": 3, "max": 7}
    float_parameter = {
        "name": "strength",
        "type": "float",
        "default_value": 0.2,
        "min_value": 0.0,
        "max_value": 1.0,
    }
    result = default_parameter_sampling_range(float_parameter)
    assert result == {"min": 0.13, "max": 0.47}
    assert default_parameter_sampling_range(
        {"name": "fixed", "type": "int", "default_value": 1, "min_value": 1, "max_value": 1}
    ) == {"min": 1, "max": 1}


def test_parameter_display_precision_matches_parameter_scale():
    assert parameter_display_precision(INT_PARAMETER) == 0
    assert parameter_display_precision(
        {"name": "strength", "type": "float", "default_value": 0.2, "min_value": 0, "max_value": 1}
    ) == 2
    assert parameter_display_precision(
        {"name": "noise", "type": "float", "default_value": 0.03, "min_value": 0, "max_value": 0.2}
    ) == 3
    assert parameter_display_precision(
        {
            "name": "learning_rate",
            "type": "float",
            "default_value": 0.0001,
            "min_value": 0.000001,
            "max_value": 0.1,
        }
    ) == 6


def test_range_is_clamped_swapped_and_equal_bounds_are_fixed():
    assert normalize_parameter_sampling_value(INT_PARAMETER, {"min": 20, "max": -3}) == {
        "min": 0,
        "max": 10,
    }
    fixed = normalize_parameter_sampling_value(INT_PARAMETER, {"min": 7, "max": 7})
    assert fixed == {"min": 7, "max": 7}
    assert parameter_sampling_is_variable(fixed) is False
    assert sample_parameter_value(INT_PARAMETER, fixed, seed="fixed") == 7


def test_range_sampling_is_bounded_and_reproducible():
    configured = normalize_parameter_sampling_value(INT_PARAMETER, {"min": 2, "max": 8})
    first = [sample_parameter_value(INT_PARAMETER, configured, seed=f"task:1:{index}") for index in range(20)]
    second = [sample_parameter_value(INT_PARAMETER, configured, seed=f"task:1:{index}") for index in range(20)]

    assert first == second
    assert all(2 <= value <= 8 for value in first)
    assert len(set(first)) > 1

    float_parameter = {
        "name": "strength",
        "type": "float",
        "default_value": 0.5,
        "min_value": 0.1,
        "max_value": 1.0,
        "options": [],
    }
    float_range = normalize_parameter_sampling_value(float_parameter, {"min": -1, "max": 2})
    assert float_range == {"min": 0.1, "max": 1.0}
    sampled_float = sample_parameter_value(float_parameter, float_range, seed="float")
    assert 0.1 <= sampled_float <= 1.0


class RecordingRunner:
    def __init__(self):
        self.payloads = []

    def run(self, payload, _context, **_kwargs):
        self.payloads.append(payload)
        index = len(self.payloads) - 1
        return {
            "ok": True,
            "outputs": [
                {
                    "source_sample_id": payload["input"]["samples"][0]["id"],
                    "output_path": f"output-{index}.png",
                    "metadata": {},
                }
            ],
            "logs": [],
        }


def _service_with_runner(runner):
    return GenerationService(
        paths=None,
        session_factory=None,
        task_manager=None,
        task_repository=None,
        algorithm_repository=None,
        dataset_repository=None,
        plugin_runner=runner,
    )


class ParameterRepository:
    def list_parameters(self, _session, algorithm_id):
        maximum = 10 if algorithm_id == 1 else 100
        return [
            SimpleNamespace(
                name="shared",
                type="int",
                default_value=5,
                min_value=0,
                max_value=maximum,
                options_json=[],
            )
        ]


def test_task_parameters_are_scoped_per_algorithm_and_clamped_independently():
    service = _service_with_runner(RecordingRunner())
    service.algorithm_repository = ParameterRepository()
    algorithms = [SimpleNamespace(id=1), SimpleNamespace(id=2)]

    normalized = service._normalize_task_parameters(
        None,
        algorithms,
        {
            "algorithm_parameters": {
                "1": {"shared": {"min": -5, "max": 20}},
                "2": {"shared": {"min": 20, "max": 80}},
            }
        },
    )

    assert normalized["algorithm_parameters"] == {
        "1": {"shared": {"min": 0, "max": 10}},
        "2": {"shared": {"min": 20, "max": 80}},
    }


def test_service_samples_each_output_and_rotates_source_samples(tmp_path):
    runner = RecordingRunner()
    service = _service_with_runner(runner)
    algorithm = SimpleNamespace(
        id=33,
        key="generation.image.linear_transform",
        module_path="plugin.module",
        callable_name="run",
        script_path=None,
    )

    result = service._run_plugin_with_parameter_sampling(
        task_id=148,
        algorithm=algorithm,
        modality="image",
        task_parameters={
            "algorithm_parameters": {
                "33": {"amount": {"min": 2, "max": 8}},
            }
        },
        parameter_contracts=[INT_PARAMETER],
        target_count=3,
        dataset_id=130,
        dataset_path="dataset",
        samples=[{"id": 1}, {"id": 2}],
        output_dir=tmp_path,
        plugin_context=object(),
    )

    assert result["ok"] is True
    assert len(runner.payloads) == 3
    assert [payload["target_count"] for payload in runner.payloads] == [1, 1, 1]
    assert [payload["input"]["samples"][0]["id"] for payload in runner.payloads] == [1, 2, 1]
    sampled = [output["metadata"]["sampled_parameters"]["amount"] for output in result["outputs"]]
    assert all(2 <= value <= 8 for value in sampled)


def test_service_keeps_equal_bounds_on_single_batch_call(tmp_path):
    runner = RecordingRunner()
    service = _service_with_runner(runner)
    algorithm = SimpleNamespace(
        id=33,
        key="generation.image.linear_transform",
        module_path="plugin.module",
        callable_name="run",
        script_path=None,
    )

    result = service._run_plugin_with_parameter_sampling(
        task_id=148,
        algorithm=algorithm,
        modality="image",
        task_parameters={"amount": {"min": 4, "max": 4}},
        parameter_contracts=[INT_PARAMETER],
        target_count=3,
        dataset_id=130,
        dataset_path="dataset",
        samples=[{"id": 1}, {"id": 2}],
        output_dir=tmp_path,
        plugin_context=object(),
    )

    assert result["ok"] is True
    assert len(runner.payloads) == 1
    assert runner.payloads[0]["target_count"] == 3
    assert runner.payloads[0]["parameters"]["amount"] == 4
