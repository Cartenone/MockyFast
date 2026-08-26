"""The documented configurations have to be configurations that load.

Every YAML block in the README is written into a sandbox holding the data files
those examples name, and handed to `load_config`. `tests/fixtures/readme-0.1.0`
does the same for the blocks the first published README documented, so a change
to the format cannot quietly break a configuration someone copied from it.
"""

import re
from pathlib import Path

import pytest
import yaml

from mockyfast.config import load_config

PROJECT_ROOT = Path(__file__).resolve().parent.parent

README = PROJECT_ROOT / "README.md"

LEGACY_CONFIGS = PROJECT_ROOT / "tests" / "fixtures" / "readme-0.1.0"

YAML_BLOCK = re.compile(r"```yaml\n(.*?)```", re.DOTALL)

USERS_JSON = """[
  { "id": 1, "name": "Mario", "role": "admin" },
  { "id": 2, "name": "Luigi", "role": "user" }
]
"""

USERS_CSV = "id,name,active,balance\n1,Mario,true,12.5\n2,Luigi,false,7\n"

COUNTRIES_CSV = "code,name\nIT,Italy\nFR,France\n"

WRAPPED_USERS_JSON = '{"users": [{"id": 1, "name": "Mario"}]}\n'


def write_example_data(root: Path) -> None:
    """The files the README's examples point at."""
    (root / "data").mkdir(parents=True, exist_ok=True)
    (root / "responses").mkdir(parents=True, exist_ok=True)

    (root / "data" / "users.json").write_text(USERS_JSON, encoding="utf-8")
    (root / "data" / "users.csv").write_text(USERS_CSV, encoding="utf-8")
    (root / "data" / "countries.csv").write_text(COUNTRIES_CSV, encoding="utf-8")
    (root / "responses" / "users.json").write_text(
        WRAPPED_USERS_JSON, encoding="utf-8"
    )


def is_config(block: str) -> bool:
    """A block is a whole configuration, not a fragment of one."""
    try:
        parsed = yaml.safe_load(block)
    except yaml.YAMLError:
        return False

    return isinstance(parsed, dict) and bool(
        parsed.keys() & {"routes", "resources"}
    )


def readme_configs() -> list[str]:
    return [
        block
        for block in YAML_BLOCK.findall(README.read_text(encoding="utf-8"))
        if is_config(block)
    ]


def legacy_configs() -> list[Path]:
    return sorted(LEGACY_CONFIGS.glob("*.yaml"))


def load_in_sandbox(tmp_path: Path, block: str) -> dict:
    write_example_data(tmp_path)

    config_path = tmp_path / "mockyfast.yaml"
    config_path.write_text(block, encoding="utf-8")

    return load_config(str(config_path))


def test_the_readme_contains_configuration_examples():
    assert len(readme_configs()) >= 10


@pytest.mark.parametrize("block", readme_configs(), ids=range(len(readme_configs())))
def test_every_readme_example_loads(tmp_path, block):
    assert load_in_sandbox(tmp_path, block)["routes"]


def test_the_first_published_readme_examples_are_kept(tmp_path):
    assert len(legacy_configs()) == 10


@pytest.mark.parametrize("path", legacy_configs(), ids=lambda path: path.stem)
def test_every_0_1_0_readme_example_still_loads(tmp_path, path):
    block = path.read_text(encoding="utf-8")

    assert load_in_sandbox(tmp_path, block)["routes"]
