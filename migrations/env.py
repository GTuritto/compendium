"""Alembic environment for Compendium.

The database URL comes from the Compendium config loader (POSTGRES_URL), not
from alembic.ini. Tests override it with `-x db_url=...`. Migrations are
hand-written; autogenerate is not used, so there is no model metadata.
"""

from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# Make the compendium package importable when alembic runs as a console script.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from compendium.config import load_config  # noqa: E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def _resolve_url() -> str:
    """Database URL: the -x db_url override, else POSTGRES_URL from config.

    SQLAlchemy needs the psycopg-3 driver named explicitly.
    """
    override = context.get_x_argument(as_dictionary=True).get("db_url")
    url = override if override else load_config().postgres_url
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


config.set_main_option("sqlalchemy.url", _resolve_url())

# Hand-written migrations: no autogenerate, no target metadata.
target_metadata = None


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
