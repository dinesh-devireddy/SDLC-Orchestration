from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import URL, create_engine, select
from sqlalchemy.pool import NullPool

from .config import Settings
from .models import Link


def make_engine(settings: Settings):
    # NullPool closes connections promptly, including on Windows before backups.
    return create_engine(
        URL.create("sqlite", database=str(settings.database_path)),
        connect_args={"check_same_thread": False, "timeout": settings.lock_timeout},
        poolclass=NullPool,
    )


def migration_config():
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).parent / "migrations"))
    return config


def initialize(settings: Settings):
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    engine = make_engine(settings)
    try:
        with engine.begin() as connection:
            config = migration_config()
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
    finally:
        engine.dispose()


def check_ready(engine, settings):
    if not settings.database_path.is_file():
        raise RuntimeError("Database missing; run python -m shortener init-db")
    with engine.connect() as connection:
        heads = MigrationContext.configure(connection).get_current_heads()
        expected = tuple(ScriptDirectory.from_config(migration_config()).get_heads())
        if set(heads) != set(expected):
            raise RuntimeError("Database migrations missing; run python -m shortener init-db")
        connection.execute(select(Link).limit(0))
