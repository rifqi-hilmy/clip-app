"""SQLite engine & session helpers."""
from __future__ import annotations

from collections.abc import Iterator

from sqlmodel import Session, SQLModel, create_engine

from .config import settings

engine = create_engine(
    f"sqlite:///{settings.db_path}",
    connect_args={"check_same_thread": False},  # worker threads share the engine
)


def init_db() -> None:
    from . import models  # noqa: F401  (register tables)

    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    SQLModel.metadata.create_all(engine)
    _migrate_columns()


# Sprint 1: create_all() never adds columns to existing tables, so patch
# new columns onto old databases here. Keep in sync with models.py.
_NEW_COLUMNS: dict[str, list[tuple[str, str]]] = {
    "clip": [
        ("loudnorm", "INTEGER NOT NULL DEFAULT 1"),
        ("review_state", "TEXT NOT NULL DEFAULT 'approved'"),
        ("safe_zone", "TEXT"),
        ("remove_silence", "INTEGER NOT NULL DEFAULT 0"),
        ("silence_db", "REAL NOT NULL DEFAULT -35.0"),
        ("silence_min_dur", "REAL NOT NULL DEFAULT 0.8"),
    ],
}


def _migrate_columns() -> None:
    import sqlite3

    with sqlite3.connect(settings.db_path) as con:
        for table, columns in _NEW_COLUMNS.items():
            existing = {row[1] for row in con.execute(f"PRAGMA table_info({table})")}
            for name, ddl in columns:
                if name not in existing:
                    con.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")
            con.commit()


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
