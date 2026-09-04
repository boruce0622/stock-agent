from pathlib import Path

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

settings = get_settings()
if settings.database_url.startswith("sqlite"):
    database_path = settings.database_url.rsplit("///", 1)[-1]
    if database_path != ":memory:":
        Path(database_path).parent.mkdir(parents=True, exist_ok=True)

engine = create_async_engine(settings.database_url)


@event.listens_for(engine.sync_engine, "connect")
def configure_sqlite(dbapi_connection, _connection_record) -> None:
    if settings.database_url.startswith("sqlite"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()


SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db():
    async with SessionLocal() as session:
        yield session
