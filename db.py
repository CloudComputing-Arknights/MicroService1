import os
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

# Env vars (set these on the Cloud Run service)
INSTANCE_CONNECTION_NAME = os.environ["INSTANCE_CONNECTION_NAME"]  # e.g. vigilant-tract-476122-d9:us-central1:users
DB_NAME  = os.getenv("DB_NAME", "users_db")
DB_USER  = os.getenv("DB_USER", "users_svc")
DB_PASS  = os.environ["DB_PASS"]  # from Secret Manager
CHARSET  = "utf8mb4"

# Build a Unix-socket DSN for aiomysql
DATABASE_URL = (
    f"mysql+aiomysql://{DB_USER}:{DB_PASS}@/{DB_NAME}"
    f"?unix_socket=/cloudsql/{INSTANCE_CONNECTION_NAME}"
    f"&charset={CHARSET}"
)

engine = create_async_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=1800,  # refresh stale conns
    future=True,
)

async def ping():
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT 1"))
        return bool(result.scalar())