from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import event

# Database file local hard drive par banegi
DATABASE_URL = "sqlite+aiosqlite:///./medical_store.db"

# Async engine setup
engine = create_async_engine(DATABASE_URL, echo=False)

# WAL mode enable karne ke liye event listener (Concurrency ke liye zaroori hai)
@event.listens_for(engine.sync_engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()

# Session maker jo har request par naya database session banayega
AsyncSessionLocal = sessionmaker(
    bind=engine, class_=AsyncSession, expire_on_commit=False
)

# Sab models is Base class ko inherit karenge
Base = declarative_base()

# Dependency injection function FastAPI ke routers ke liye
async def get_db():
    async with AsyncSessionLocal() as session:
        yield session