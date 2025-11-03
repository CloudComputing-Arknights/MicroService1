import os
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from google.cloud.sql.connector import Connector, IPTypes

INSTANCE_CONN_NAME = os.getenv("INSTANCE_CONNECTION_NAME")  # "project:region:instance"
DB_NAME = os.getenv("DB_NAME", "users_db")
DB_USER = os.getenv("DB_USER", "users_svc")
DB_PASS = os.getenv("DB_PASS")  # injected via Secret Manager / env var
USE_PRIVATE_IP = os.getenv("USE_PRIVATE_IP", "0") == "1"

_connector = Connector()

async def _getconn():
    return await _connector.connect_async(
        INSTANCE_CONN_NAME,
        driver="asyncmy",
        user=DB_USER,
        password=DB_PASS,
        db=DB_NAME,
        ip_type=IPTypes.PRIVATE if USE_PRIVATE_IP else IPTypes.PUBLIC,
    )

engine = create_async_engine(
    "mysql+asyncmy://",
    async_creator=_getconn,
    pool_pre_ping=True,
    pool_recycle=1800,
)

async def ping():
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT 1"))
        return bool(result.scalar())

def close_connector():
    _connector.close()