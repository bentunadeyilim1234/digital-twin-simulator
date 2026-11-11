import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from twin_engine import default_config  # noqa: E402
from twin_engine.scenarios import instantiate_template  # noqa: E402


@pytest.fixture()
def cfg():
    return default_config()


@pytest.fixture()
def baseline(cfg):
    return instantiate_template(cfg, "S0")


@pytest.fixture()
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setenv("TWIN_DB_PATH", str(tmp_path / "test.sqlite3"))
    return tmp_path / "test.sqlite3"
