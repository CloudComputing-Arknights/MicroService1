import os
from sqlalchemy import create_engine, text
from google.cloud.sql.connector import Connector, IPTypes
import pymysql  # required by the connector/SQLAlchemy combo

INSTANCE_CONN_NAME = os.getenv("INSTANCE_CONNECTION_NAME")  # "project:region:instance"
DB_NAME = os.getenv("DB_NAME", "users_db")
DB_USER = os.getenv("DB_USER", "users_svc")
DB_PASS = os.getenv("DB_PASS")  # injected via Secret Manager / env var
USE_PRIVATE_IP = os.getenv("USE_PRIVATE_IP", "0") == "1"

connector = Connector()

def getconn():
    return connector.connect(
        INSTANCE_CONN_NAME,
        "pymysql",
        user=DB_USER,
        password=DB_PASS,
        db=DB_NAME,
        ip_type=IPTypes.PRIVATE if USE_PRIVATE_IP else IPTypes.PUBLIC,
    )

engine = create_engine(
    "mysql+pymysql://",
    creator=getconn,
    pool_pre_ping=True,
    pool_recycle=1800,
)

def ping():
    with engine.connect() as conn:
        return bool(conn.execute(text("SELECT 1")).scalar())
