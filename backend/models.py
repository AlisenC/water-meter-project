from sqlalchemy import Table, Column, Integer, String, Float, DateTime
from datetime import datetime
from .database import metadata

readings = Table(
    "readings",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("household", String, nullable=False),
    Column("amount", Float, nullable=False),
    Column("timestamp", DateTime, default=datetime.utcnow)
)
