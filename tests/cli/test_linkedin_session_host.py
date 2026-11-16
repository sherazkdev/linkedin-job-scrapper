from pathlib import Path

from app.modules.collection.linkedin.host_login import (
    resolve_host_output_path,
    running_in_container,
)


def test_running_in_container_matches_dockerenv() -> None:
    expected = Path("/.dockerenv").is_file()
    assert running_in_container() is expected


def test_resolve_host_output_path_default() -> None:
    path = resolve_host_output_path(None)
    assert path.name == "storage_state.json"
    assert "data" in path.parts and "linkedin" in path.parts


def test_resolve_host_output_path_override(tmp_path: Path) -> None:
    custom = tmp_path / "custom.json"
    assert resolve_host_output_path(str(custom)) == custom