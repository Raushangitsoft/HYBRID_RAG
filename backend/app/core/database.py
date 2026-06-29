from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.core.config import settings

engine = create_async_engine(
    settings.POSTGRES_URL,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    echo=False,
)

AsyncSessionLocal = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


class Base(DeclarativeBase):
    pass


async def init_db():
    from app.models import document  # noqa: F401 — registers models
    from sqlalchemy.exc import IntegrityError, ProgrammingError

    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    except (IntegrityError, ProgrammingError) as exc:
        # Multiple uvicorn workers can race to create the same
        # tables/enum types on startup. If another worker already
        # created it, Postgres raises a duplicate-object error here —
        # safe to ignore since the schema now exists either way.
        if "already exists" in str(exc) or "duplicate" in str(exc).lower():
            pass
        else:
            raise


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
