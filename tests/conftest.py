import os

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.shared.db import Base
import app.shared.models  # noqa

TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL", "sqlite+aiosqlite:///./test_cb.db"
)


def _engine_kwargs():
    if TEST_DB_URL.startswith("sqlite"):
        return {"connect_args": {"check_same_thread": False}}
    return {}


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def db_engine():
    engine = create_async_engine(TEST_DB_URL, **_engine_kwargs())
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture(loop_scope="session")
async def db_session(db_engine):
    async with db_engine.connect() as conn:
        await conn.begin()
        session = AsyncSession(conn, expire_on_commit=False)
        yield session
        await conn.rollback()
