import warnings

import pytest

from clf import load_case

warnings.filterwarnings("ignore", message=".*numba.*")


@pytest.fixture(scope="session")
def net118():
    return load_case("case118")


@pytest.fixture(scope="session")
def net300():
    return load_case("case300")
