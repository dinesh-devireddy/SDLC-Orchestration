"""Never allow test connections outside pytest's temporary directory."""
from pathlib import Path

import pytest
from sqlalchemy import event
from sqlalchemy.engine import Engine


@pytest.fixture(autouse=True)
def temporary_database_only(tmp_path):
    def guard(dialect, record, args, kwargs):
        database = Path(args[0]).resolve()
        assert database.is_relative_to(tmp_path), "Tests must use this test's temporary SQLite file"

    # Refuse the connection before SQLite can create a file.
    event.listen(Engine, "do_connect", guard)
    yield
    event.remove(Engine, "do_connect", guard)
