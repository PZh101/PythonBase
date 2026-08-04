# Database Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the async SQLAlchemy database layer described in `docs/superpowers/specs/2026-08-04-database-layer-design.md`.

**Architecture:** Add a focused `pkg.database` package for declarative base, dialect mapping, URL construction, manager lifecycle, FastAPI dependencies, exceptions, and CRUD. Keep compatibility by making `pkg.common.db_crud` re-export the new CRUD and Base.

**Tech Stack:** Python 3.12, SQLAlchemy 2.x async APIs, FastAPI dependency generators, Pydantic settings models, pytest with synchronous `asyncio.run()` test wrappers.

---

## File Structure

- Create `pkg/database/base.py`: SQLAlchemy 2.x `DeclarativeBase`.
- Create `pkg/database/exceptions.py`: database initialization exception hierarchy.
- Create `pkg/database/dialects.py`: `DatabaseType` to async driver mapping.
- Create `pkg/database/url.py`: `URL.create()`, connect args, and sanitized connection descriptions.
- Create `pkg/database/manager.py`: async engine/sessionmaker lifecycle and session/transaction context managers.
- Create `pkg/database/dependencies.py`: FastAPI dependency adapters using a manager.
- Create `pkg/database/crud.py`: async `BaseCrud` that never commits or rolls back.
- Create `pkg/database/__init__.py`: public exports.
- Modify `pkg/common/db_crud.py`: compatibility re-export.
- Create `tests/pkg/database/test_url.py`: dialect, URL, connect args, and sanitization tests.
- Create `tests/pkg/database/test_manager.py`: manager lifecycle, idempotency, session, transaction, and dependency tests.
- Create `tests/pkg/database/test_crud.py`: CRUD compatibility and transaction semantics tests with fake async sessions.

### Task 1: URL And Dialect Helpers

**Files:**
- Create: `pkg/database/exceptions.py`
- Create: `pkg/database/dialects.py`
- Create: `pkg/database/url.py`
- Test: `tests/pkg/database/test_url.py`

- [ ] **Step 1: Write failing tests**

```python
from sqlalchemy.engine import URL

from pkg.config import DatabaseSettings, DatabaseType
from pkg.database.dialects import get_async_driver, get_async_drivername
from pkg.database.url import build_async_database_url, build_connect_args, describe_database


def test_mysql_and_postgresql_driver_mapping():
    assert get_async_driver(DatabaseType.MYSQL) == "asyncmy"
    assert get_async_drivername(DatabaseType.POSTGRESQL) == "postgresql+asyncpg"


def test_url_uses_sqlalchemy_url_create_and_preserves_secret_characters():
    settings = DatabaseSettings(password="p@ss:word/with#chars")
    url = build_async_database_url(settings)

    assert isinstance(url, URL)
    assert url.drivername == "mysql+asyncmy"
    assert url.password == "p@ss:word/with#chars"


def test_connect_args_follow_database_type():
    assert build_connect_args(DatabaseSettings(type="mysql", connect_timeout=2.5)) == {"connect_timeout": 2.5}
    assert build_connect_args(DatabaseSettings(type="postgresql", connect_timeout=3)) == {"timeout": 3.0}


def test_description_does_not_include_password_or_username():
    settings = DatabaseSettings(username="root", password="super-secret")
    description = describe_database(settings)

    assert description == "mysql://127.0.0.1:3306/pythonbase"
    assert "root" not in description
    assert "super-secret" not in description
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/pkg/database/test_url.py -q`
Expected: FAIL because `pkg.database` does not exist.

- [ ] **Step 3: Implement helpers**

Use `DatabaseType` from `pkg.config`, SQLAlchemy `URL.create()`, and raise `UnsupportedDatabaseTypeError` for unsupported values.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/pkg/database/test_url.py -q`
Expected: PASS.

### Task 2: Async Database Manager And Dependencies

**Files:**
- Create: `pkg/database/manager.py`
- Create: `pkg/database/dependencies.py`
- Modify: `pkg/database/__init__.py`
- Test: `tests/pkg/database/test_manager.py`

- [ ] **Step 1: Write failing tests**

```python
import asyncio
from unittest.mock import AsyncMock, Mock

from pkg.config import DatabaseSettings
from pkg.database.manager import AsyncDatabaseManager
from pkg.database.dependencies import create_db_session_dependency, create_readonly_db_session_dependency


def run(coro):
    return asyncio.run(coro)


def test_initialize_creates_engine_once(monkeypatch):
    engine = Mock()
    engine.begin.return_value.__aenter__ = AsyncMock()
    engine.begin.return_value.__aexit__ = AsyncMock(return_value=None)
    monkeypatch.setattr("pkg.database.manager.create_async_engine", Mock(return_value=engine))
    monkeypatch.setattr("pkg.database.manager.async_sessionmaker", Mock(return_value=Mock()))

    manager = AsyncDatabaseManager(DatabaseSettings(startup_check=False))
    run(manager.initialize())
    run(manager.initialize())

    assert manager.engine is engine


def test_transaction_commits_and_rolls_back():
    session = AsyncMock()
    factory = Mock(return_value=session)
    manager = AsyncDatabaseManager(DatabaseSettings(startup_check=False))
    manager._session_factory = factory

    async def scenario():
        async with manager.transaction() as yielded:
            assert yielded is session
        assert session.commit.await_count == 1
        try:
            async with manager.transaction():
                raise RuntimeError("boom")
        except RuntimeError:
            pass

    run(scenario())
    assert session.rollback.await_count == 1
    assert session.close.await_count == 2


def test_dependencies_delegate_to_manager_transaction_and_session():
    manager = AsyncDatabaseManager(DatabaseSettings(startup_check=False))
    tx_session = object()
    read_session = object()

    class Ctx:
        def __init__(self, value):
            self.value = value
        async def __aenter__(self):
            return self.value
        async def __aexit__(self, exc_type, exc, tb):
            return None

    manager.transaction = Mock(return_value=Ctx(tx_session))
    manager.session = Mock(return_value=Ctx(read_session))

    async def scenario():
        dep = create_db_session_dependency(manager)
        readonly_dep = create_readonly_db_session_dependency(manager)
        assert await dep.__anext__() is tx_session
        assert await readonly_dep.__anext__() is read_session

    run(scenario())
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/pkg/database/test_manager.py -q`
Expected: FAIL because manager and dependency modules do not exist.

- [ ] **Step 3: Implement manager and dependencies**

Implement idempotent `initialize()`, `dispose()`, `session()`, `transaction()`, `check_connection()`, `create_db_session_dependency()`, and `create_readonly_db_session_dependency()`.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/pkg/database/test_manager.py -q`
Expected: PASS.

### Task 3: CRUD Migration And Compatibility

**Files:**
- Create: `pkg/database/base.py`
- Create: `pkg/database/crud.py`
- Modify: `pkg/common/db_crud.py`
- Modify: `pkg/database/__init__.py`
- Test: `tests/pkg/database/test_crud.py`

- [ ] **Step 1: Write failing tests**

```python
import asyncio
from unittest.mock import AsyncMock, Mock

from sqlalchemy import Integer
from sqlalchemy.orm import Mapped, mapped_column

from pkg.common.db_crud import BaseCrud as LegacyBaseCrud
from pkg.database.base import Base
from pkg.database.crud import BaseCrud


class User(Base):
    __tablename__ = "test_users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str]


def run(coro):
    return asyncio.run(coro)


def test_legacy_import_reexports_new_crud():
    assert LegacyBaseCrud is BaseCrud


def test_create_flushes_and_refreshes_without_commit():
    session = AsyncMock()
    crud = BaseCrud(User)

    created = run(crud.create(session, {"id": 1, "name": "Ada"}))

    assert created.id == 1
    assert created.name == "Ada"
    session.add.assert_called_once_with(created)
    session.flush.assert_awaited_once()
    session.refresh.assert_awaited_once_with(created)
    session.commit.assert_not_called()


def test_update_returns_none_when_missing_and_does_not_commit():
    session = AsyncMock()
    result = Mock()
    result.scalars.return_value.first.return_value = None
    session.execute.return_value = result
    crud = BaseCrud(User)

    updated = run(crud.update(session, 404, {"name": "Grace"}))

    assert updated is None
    session.commit.assert_not_called()


def test_delete_flushes_without_commit():
    session = AsyncMock()
    result = Mock(rowcount=1)
    session.execute.return_value = result
    crud = BaseCrud(User)

    deleted = run(crud.delete_by_id(session, 1))

    assert deleted is True
    session.flush.assert_awaited_once()
    session.commit.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/pkg/database/test_crud.py -q`
Expected: FAIL because new CRUD is not implemented and legacy path has old commit behavior.

- [ ] **Step 3: Implement CRUD and compatibility exports**

Move CRUD into `pkg.database.crud`, change writes to `flush()` plus `refresh()` when returning objects, and re-export from `pkg.common.db_crud`.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/pkg/database/test_crud.py -q`
Expected: PASS.

### Task 4: Full Verification

**Files:**
- No new files.

- [ ] **Step 1: Run focused database tests**

Run: `uv run pytest tests/pkg/database -q`
Expected: PASS.

- [ ] **Step 2: Run full test suite**

Run: `uv run pytest -q`
Expected: PASS.

## Self-Review

- Spec coverage: URL construction, dialect mapping, manager lifecycle, FastAPI adapters, CRUD transaction semantics, old import compatibility, and credential-safe descriptions are covered.
- Placeholder scan: no `TBD`, `TODO`, or undefined implementation placeholders remain.
- Type consistency: tests and planned modules use `DatabaseSettings`, `DatabaseType`, `AsyncDatabaseManager`, and `BaseCrud` consistently.
