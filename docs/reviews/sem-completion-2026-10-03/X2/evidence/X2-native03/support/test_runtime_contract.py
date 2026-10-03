"""Offline boundary checks against the actual native9f startup contract."""
from pathlib import Path
from urllib.parse import unquote, urlparse

import native_probe as n
import probe_models as m
import pytest


def test_existing_directory_and_file_uri_before_session(tmp_path: Path) -> None:
    output = tmp_path.resolve() / "owned-output"
    output.mkdir()
    n.prepare_runtime_directories(output)
    plan_path = Path(__file__).parents[2] / "X2-native02/queue01/x2-reference-p16-01.json"
    plan = m.Plan.model_validate_json(plan_path.read_bytes()).model_copy(update={"output": output})
    env = n.environment(plan)
    parsed = urlparse(env["SAIL_GRAPH_UTILS_ROOT"])
    assert parsed.scheme == "file"
    assert Path(unquote(parsed.path)) == output / "staging"
    assert Path(unquote(parsed.path)).is_dir()
    assert env["SAIL_EXPERIMENTAL_EXTENSIONS"] == "1"


def test_missing_owned_parent_is_not_silently_created(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="canonical fresh owned"):
        n.prepare_runtime_directories(tmp_path.resolve() / "missing-output")


def test_actual_rust_requires_uri_and_existing_local_directory() -> None:
    source = n.GRAPH_SOURCE / "crates/sail-session/src/extensions"
    assert 'as_deref() != Ok("1")' in (source / "mod.rs").read_text()
    assert "Url::parse(root)" in (source / "graph_utils/storage.rs").read_text()
    local = (source / "graph_utils/local.rs").read_text()
    assert "to_file_path()" in local and "path.canonicalize()" in local
    assert "precreate the trusted graph staging directory before starting Sail" in local
