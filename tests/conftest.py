from datetime import datetime
from pathlib import Path

import pytest

from emporio.catalog import Catalog
from emporio.orders import OrderBook

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


@pytest.fixture(scope="session")
def data_dir() -> Path:
    return DATA_DIR


@pytest.fixture(scope="session")
def catalog() -> Catalog:
    return Catalog(DATA_DIR)


@pytest.fixture(scope="session")
def book(catalog: Catalog) -> OrderBook:
    return OrderBook(DATA_DIR, catalog)


@pytest.fixture
def now() -> datetime:
    return datetime(2026, 10, 28, 14, 0)
