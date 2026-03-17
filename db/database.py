from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from config import settings

# Thin mode — no Oracle Instant Client required, works with ADB wallet
connect_args: dict = {}
if settings.ORACLE_WALLET_DIR:
    connect_args = {
        "config_dir": settings.ORACLE_WALLET_DIR,
        "wallet_location": settings.ORACLE_WALLET_DIR,
        "wallet_password": settings.ORACLE_WALLET_PASSWORD,
    }

engine = create_async_engine(
    settings.db_url,
    connect_args=connect_args,
    pool_size=5,
    max_overflow=10,
    echo=False,
)

AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
