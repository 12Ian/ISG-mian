import ast
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database import Base
from backend.models import Algorithm, AlgorithmParameter
from backend.parameter_ranges import normalize_parameter_type, normalized_parameter_range
from backend.plugins.contracts import load_plugin_parameters
from backend.qt.bridge import BackendBridge
from backend.repositories.algorithm_repository import AlgorithmRepository
from backend.seed_data import DEFAULT_ALGORITHMS


ROOT = Path(__file__).resolve().parent.parent


def test_all_default_algorithms_use_plugin_parameter_contracts():
    assert len(DEFAULT_ALGORITHMS) == 69
    assert sum(len(item["parameters"]) for item in DEFAULT_ALGORITHMS) == 233

    for algorithm in DEFAULT_ALGORITHMS:
        assert algorithm["parameters"] == load_plugin_parameters(ROOT, algorithm["module_path"])
        for parameter in algorithm["parameters"]:
            range_info = normalized_parameter_range(parameter)
            default = parameter["default"]
            if parameter["type"] not in {"int", "float"}:
                continue
            assert range_info["min_value"] <= default <= range_info["max_value"]


def test_runtime_clamps_match_declared_plugin_ranges():
    checked = 0
    for algorithm in DEFAULT_ALGORITHMS:
        parameters = {item["name"]: item for item in algorithm["parameters"]}
        script_path = ROOT.joinpath(*algorithm["module_path"].split(".")).with_suffix(".py")
        tree = ast.parse(script_path.read_text(encoding="utf-8-sig"), filename=str(script_path))
        for call in (node for node in ast.walk(tree) if isinstance(node, ast.Call)):
            function_name = _call_name(call)
            if function_name not in {"_clamp", "_clamp_float", "_clamp_int", "clamp_float", "clamp_int"}:
                continue
            if len(call.args) < 3:
                continue
            parameter_name = _parameter_name(call.args[0])
            min_value = _number(call.args[1])
            max_value = _number(call.args[2])
            if parameter_name not in parameters or min_value is None or max_value is None:
                continue
            range_info = normalized_parameter_range(parameters[parameter_name])
            assert (range_info["min_value"], range_info["max_value"]) == (
                float(min_value),
                float(max_value),
            ), f"{algorithm['key']}.{parameter_name}"
            runtime_default = _parameter_default(call.args[0], parameter_name)
            if runtime_default is not None:
                assert runtime_default == parameters[parameter_name]["default"], (
                    f"{algorithm['key']}.{parameter_name}"
                )
            checked += 1
    assert checked >= 69


def test_database_sync_replaces_every_default_algorithm_parameter():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, future=True)
    repository = AlgorithmRepository(session_factory)

    with session_factory() as session:
        for item in DEFAULT_ALGORITHMS:
            algorithm = Algorithm(
                key=item["key"],
                name=item["name"],
                category=item["category"],
                modality=item["modality"],
                entry_type=item["entry_type"],
            )
            session.add(algorithm)
            session.flush()
            session.add(
                AlgorithmParameter(
                    algorithm_id=algorithm.id,
                    name="stale_parameter",
                    label="stale_parameter",
                    type="string",
                    default_value="stale",
                )
            )
        session.commit()

    bridge = BackendBridge(
        facade=SimpleNamespace(
            session_factory=session_factory,
            algorithm_repository=repository,
        )
    )
    bridge._sync_default_algorithm_parameters(DEFAULT_ALGORITHMS)

    expected_by_key = {item["key"]: item["parameters"] for item in DEFAULT_ALGORITHMS}
    with session_factory() as session:
        algorithms = session.query(Algorithm).all()
        for algorithm in algorithms:
            actual = repository.list_parameters(session, algorithm.id)
            expected = expected_by_key[algorithm.key]
            assert len(actual) == len(expected)
            for model, parameter in zip(actual, expected):
                range_info = normalized_parameter_range(parameter)
                assert model.name == parameter["name"]
                assert model.type == normalize_parameter_type(parameter["type"])
                assert model.default_value == parameter["default"]
                assert model.min_value == range_info["min_value"]
                assert model.max_value == range_info["max_value"]
                assert model.options_json == range_info["options"]

        parameter_ids = [item.id for item in session.query(AlgorithmParameter).order_by(AlgorithmParameter.id)]

    bridge._sync_default_algorithm_parameters(DEFAULT_ALGORITHMS)
    with session_factory() as session:
        assert [
            item.id for item in session.query(AlgorithmParameter).order_by(AlgorithmParameter.id)
        ] == parameter_ids


def test_qml_does_not_define_algorithm_defaults():
    qml = (ROOT / "ui" / "views" / "SampleGenView.qml").read_text(encoding="utf-8")
    assert "imageStrongDefaultValue" not in qml
    assert "strongDefault" not in qml


def _call_name(call: ast.Call) -> str:
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return ""


def _parameter_name(node: ast.AST):
    for child in ast.walk(node):
        if not isinstance(child, ast.Call) or not isinstance(child.func, ast.Attribute):
            continue
        if child.func.attr != "get" or not child.args:
            continue
        owner = child.func.value
        name = child.args[0]
        if isinstance(owner, ast.Name) and owner.id in {"parameters", "params"}:
            if isinstance(name, ast.Constant) and isinstance(name.value, str):
                return name.value
    return None


def _number(node: ast.AST):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        value = _number(node.operand)
        return -value if value is not None else None
    return None


def _parameter_default(node: ast.AST, parameter_name: str):
    for child in ast.walk(node):
        if not isinstance(child, ast.Call) or not isinstance(child.func, ast.Attribute):
            continue
        if child.func.attr != "get" or len(child.args) < 2:
            continue
        owner = child.func.value
        name = child.args[0]
        if not isinstance(owner, ast.Name) or owner.id not in {"parameters", "params"}:
            continue
        if not isinstance(name, ast.Constant) or name.value != parameter_name:
            continue
        try:
            return ast.literal_eval(child.args[1])
        except (TypeError, ValueError):
            return None
    return None
