import pytest

from pedalfleet.kit import load_kit
from pedalfleet.paths import KIT_DIR
from tests.helpers import write_project


@pytest.fixture
def kit():
    return load_kit(KIT_DIR)


@pytest.fixture
def board(tmp_path):
    return write_project(tmp_path / "fx-Test", "fx-Test")


@pytest.fixture
def template(tmp_path):
    return write_project(tmp_path / "templates" / "TestTemplate", "tpl-Test", kind="template")
