import pytest
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from config import settings
from db.database import Base

@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture(scope="session")
async def test_engine():
    # We use the same DB but could theoretically use a test one
    engine = create_async_engine(settings.database_url, echo=False)
    yield engine
    await engine.dispose()

@pytest.fixture
async def db_session(test_engine):
    Session = async_sessionmaker(test_engine, expire_on_commit=False, class_=AsyncSession)
    async with Session() as session:
        yield session
