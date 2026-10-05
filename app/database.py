import logging
import threading
import time
from contextlib import contextmanager

from sqlalchemy import MetaData, inspect, text
from sqlalchemy.engine.reflection import Inspector
from sqlalchemy.exc import DBAPIError, OperationalError, ProgrammingError
from sqlmodel import SQLModel, Session, create_engine

from app.config import get_settings

logger = logging.getLogger(__name__)

_schema_lock = threading.Lock()


def sqlalchemy_uri(uri: str) -> str:
    """Accept Render's postgres:// URLs in the sync SQLAlchemy engine."""
    if uri.startswith("postgres://"):
        return "postgresql+psycopg2://" + uri[len("postgres://") :]
    if uri.startswith("postgresql://"):
        return "postgresql+psycopg2://" + uri[len("postgresql://") :]
    return uri


engine = create_engine(
    sqlalchemy_uri(get_settings().database_uri),
    echo=get_settings().env.lower()
    in ["dev", "development", "test", "testing", "staging"],
    pool_size=get_settings().db_pool_size,
    max_overflow=get_settings().db_additional_overflow,
    pool_timeout=get_settings().db_pool_timeout,
    pool_recycle=get_settings().db_pool_recycle,
)


def create_db_and_tables() -> None:
    # Ensure model modules are imported so tables are registered on metadata.
    import app.models  # noqa: F401

    SQLModel.metadata.create_all(engine)
    _upgrade_semester_plan_schema()


def _upgrade_semester_plan_schema() -> None:
    """Add columns introduced after existing workflow tables were created."""
    inspector = inspect(engine)
    if inspector.has_table("semester_plan"):
        columns = {
            column["name"] for column in inspector.get_columns("semester_plan")
        }
        if "submitted_at" not in columns:
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "ALTER TABLE semester_plan "
                        "ADD COLUMN submitted_at TIMESTAMP"
                    )
                )
            logger.info("Added nullable semester_plan.submitted_at column")

        _remove_student_semester_unique_constraint(inspector)

    if inspector.has_table("advisor"):
        columns = {column["name"] for column in inspector.get_columns("advisor")}
        if "user_id" not in columns:
            with engine.begin() as connection:
                connection.execute(
                    text(
                        'ALTER TABLE advisor ADD COLUMN user_id INTEGER '
                        'REFERENCES "user"(id)'
                    )
                )
            logger.info("Added nullable advisor.user_id column")

        with engine.begin() as connection:
            connection.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS "
                    "ix_advisor_user_id ON advisor (user_id)"
                )
            )


def _remove_student_semester_unique_constraint(inspector: Inspector) -> None:
    constraints = [
        constraint
        for constraint in inspector.get_unique_constraints("semester_plan")
        if set(constraint.get("column_names") or ())
        == {"student_id", "semester_id"}
    ]
    if not constraints:
        return

    if engine.dialect.name == "sqlite":
        _rebuild_semester_plan_without_pair_constraint()
    elif engine.dialect.name == "postgresql":
        preparer = engine.dialect.identifier_preparer
        with engine.begin() as connection:
            for constraint in constraints:
                name = constraint.get("name")
                if name is None:
                    raise RuntimeError(
                        "Cannot remove an unnamed semester_plan constraint."
                    )
                quoted_name = preparer.quote(name)
                connection.execute(
                    text(
                        f"ALTER TABLE semester_plan "
                        f"DROP CONSTRAINT {quoted_name}"
                    )
                )
    else:
        raise RuntimeError(
            "Removing the semester-plan uniqueness constraint is unsupported "
            f"for {engine.dialect.name}."
        )
    logger.info(
        "Removed unique semester_plan(student_id, semester_id) constraint"
    )


def _rebuild_semester_plan_without_pair_constraint() -> None:
    source_table = SQLModel.metadata.tables["semester_plan"]
    temporary_name = "semester_plan_rebuild"
    preparer = engine.dialect.identifier_preparer
    quoted_columns = ", ".join(
        preparer.quote(column.name) for column in source_table.columns
    )
    if inspect(engine).has_table(temporary_name):
        raise RuntimeError(
            f"Cannot rebuild semester_plan: {temporary_name} already exists."
        )

    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        connection.commit()
        try:
            connection.exec_driver_sql("BEGIN IMMEDIATE")
            migration_metadata = MetaData()
            for referenced_table in ("student", "semester"):
                SQLModel.metadata.tables[referenced_table].to_metadata(
                    migration_metadata
                )
            replacement_table = source_table.to_metadata(
                migration_metadata,
                name=temporary_name,
            )
            replacement_table.create(connection)
            connection.execute(
                text(
                    f"INSERT INTO {preparer.quote(temporary_name)} "
                    f"({quoted_columns}) "
                    f"SELECT {quoted_columns} FROM "
                    f"{preparer.quote('semester_plan')}"
                )
            )
            connection.exec_driver_sql("DROP TABLE semester_plan")
            connection.exec_driver_sql(
                f"ALTER TABLE {preparer.quote(temporary_name)} "
                "RENAME TO semester_plan"
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
            connection.commit()


def drop_all() -> None:
    SQLModel.metadata.drop_all(bind=engine)


def is_db_not_ready_error(exc: BaseException) -> bool:
    """True when Postgres is unreachable or the schema/tables are missing."""
    if isinstance(exc, OperationalError):
        return True
    if isinstance(exc, ProgrammingError):
        return True
    if isinstance(exc, DBAPIError) and getattr(exc, "connection_invalidated", False):
        return True

    text = str(exc).lower()
    markers = (
        "does not exist",
        "undefinedtable",
        "undefined table",
        "no such table",
        "relation ",
        "could not connect",
        "connection refused",
        "connection timed out",
        "server closed the connection",
        "the database system is starting up",
        "remaining connection slots",
        "too many connections",
        "ssl connection has been closed",
    )
    return any(m in text for m in markers)


def ensure_db_and_tables(
    *,
    retries: int = 8,
    delay_seconds: float = 2.0,
) -> None:
    """Create tables, retrying while the prod DB is still coming up."""
    last: BaseException | None = None
    for attempt in range(1, retries + 1):
        try:
            with _schema_lock:
                create_db_and_tables()
            if attempt > 1:
                logger.info("Database schema ready after %s attempt(s)", attempt)
            return
        except Exception as exc:  # noqa: BLE001 — first-boot resilience
            last = exc
            if not is_db_not_ready_error(exc) or attempt >= retries:
                raise
            logger.warning(
                "Database not ready (attempt %s/%s): %s",
                attempt,
                retries,
                exc,
            )
            time.sleep(delay_seconds * attempt)
    if last is not None:
        raise last


def recover_if_uninitialized(exc: BaseException) -> bool:
    """If *exc* looks like a missing schema, create tables and return True."""
    if not is_db_not_ready_error(exc):
        return False
    logger.warning("Uninitialized database detected; creating tables: %s", exc)
    ensure_db_and_tables()
    return True


def _session_generator():
    with Session(engine) as session:
        try:
            yield session
        except Exception as e:
            logger.error(f"Database session error: {e}")
            raise
        finally:
            session.close()


def get_session():
    yield from _session_generator()


@contextmanager
def get_cli_session():
    yield from _session_generator()
