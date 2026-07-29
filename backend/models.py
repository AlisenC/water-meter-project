from sqlalchemy import Column, Integer, Float, String, DateTime
from datetime import datetime
from .database import Base

class Reading(Base):
    __tablename__ = "readings"

    id = Column(Integer, primary_key=True, index=True)
    mi = Column(String)
    reading = Column(Float)
    record_date = Column(DateTime)
    unit = Column(Integer)


class BillingStatement(Base):
    __tablename__ = "billing_statements"

    id = Column(Integer, primary_key=True, index=True)
    billing_month = Column(Integer, nullable=False)
    billing_year = Column(Integer, nullable=False)
    period_end_month = Column(Integer, nullable=True)
    period_end_year = Column(Integer, nullable=True)
    total_units_consumed = Column(Float, nullable=False)
    total_cost = Column(Float, nullable=False)
    cost_per_unit = Column(Float, nullable=True)
    source_filename = Column(String, nullable=True)
    imported_at = Column(DateTime, nullable=False)


class OracleProfile(Base):
    __tablename__ = "oracle_profiles"

    id             = Column(Integer, primary_key=True, autoincrement=True)
    name           = Column(String, nullable=False)
    wallet_path    = Column(String, nullable=False)
    service_name   = Column(String, nullable=False)
    username       = Column(String, nullable=False)
    password       = Column(String, nullable=False)
    wallet_password= Column(String, nullable=True)
    created_at     = Column(DateTime, default=datetime.utcnow)
