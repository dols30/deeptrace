"""Engine lifecycle. Tests and requests read the database URL at call time."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, event, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from deeptrace.config import settings
from deeptrace.db.models import Base, Role

_engine: Engine | None = None
_engine_url: str | None = None
_session_factory: sessionmaker[Session] | None = None
_ready: set[str] = set()

ROLES = {
    "investigator": "Creates analyses, reviews findings, and edits draft reports.",
    "forensic_reviewer": "Reviews escalated findings and adds expert comments.",
    "supervisor": "Reviews reports, requests changes, and finalizes where policy permits.",
    "administrator": "Manages users, roles, model configuration, and system settings.",
}


def reset_engine() -> None:
    global _engine, _engine_url, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _engine_url = None
    _session_factory = None
    _ready.clear()


def get_engine() -> Engine:
    global _engine, _engine_url, _session_factory
    url = settings.database_url
    if _engine is not None and _engine_url != url:
        reset_engine()
    if _engine is None:
        if url.startswith("sqlite:///"):
            path = url.removeprefix("sqlite:///")
            if path and path != ":memory:":
                Path(path).parent.mkdir(parents=True, exist_ok=True)
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        _engine = create_engine(url, connect_args=connect_args, future=True)
        _engine_url = url
        _session_factory = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False, future=True)
    return _engine


@event.listens_for(Engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
    if dbapi_connection.__class__.__module__.startswith("sqlite3"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def init_db() -> None:
    engine = get_engine()
    key = str(engine.url)
    if key in _ready:
        return
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        existing = set(session.scalars(select(Role.name)))
        for name, description in ROLES.items():
            if name not in existing:
                session.add(Role(name=name, description=description))
        session.commit()
    _ready.add(key)


@contextmanager
def session_scope() -> Iterator[Session]:
    init_db()
    if _session_factory is None:
        raise RuntimeError("Database session factory is not initialized")
    session = _session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_session() -> Iterator[Session]:
    with session_scope() as session:
        yield session
