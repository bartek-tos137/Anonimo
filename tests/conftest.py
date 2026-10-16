from pathlib import Path

import pytest

from anonimo.config import load_policy
from anonimo.engine import Engine


@pytest.fixture
def policy():
    return load_policy(Path(__file__).resolve().parents[1] / "policy.yaml")


@pytest.fixture
def engine(policy):
    return Engine(policy)
