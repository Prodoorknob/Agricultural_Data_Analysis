from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


def _create_engine():
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from backend.config import get_settings

    settings = get_settings()
    engine = create_async_engine(
        settings.DATABASE_URL,
        echo=False,
        pool_size=5,
        max_overflow=10,
    )
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return engine, session_factory


_engine = None
_async_session_factory = None


def _init():
    global _engine, _async_session_factory
    if _engine is None:
        _engine, _async_session_factory = _create_engine()


async def get_db():
    _init()
    async with _async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
