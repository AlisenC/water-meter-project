from sqlalchemy import Column, Integer, Float, String, DateTime, ForeignKey, Boolean, UniqueConstraint
from datetime import datetime
from .database import Base

class Reading(Base):
    __tablename__ = "readings"
    __table_args__ = (
        UniqueConstraint("mi", "record_date", name="uq_readings_mi_record_date"),
    )

    id = Column(Integer, primary_key=True, index=True)
    mi = Column(String)
    reading = Column(Float)
    record_date = Column(DateTime)
    unit = Column(Integer)


class BillingStatement(Base):
    __tablename__ = "billing_statements"

    id = Column(Integer, primary_key=True, index=True)
    billing_month = Column(Integer, nullable=True)
    billing_year = Column(Integer, nullable=True)
    period_end_month = Column(Integer, nullable=True)
    period_end_year = Column(Integer, nullable=True)
    total_units_consumed = Column(Float, nullable=True)
    total_cost = Column(Float, nullable=True)
    cost_per_unit = Column(Float, nullable=True)
    source_filename = Column(String, nullable=True)
    imported_at = Column(DateTime, nullable=False)
    # Set when a statement's fields aren't known yet — either a PDF import failed
    # automatic extraction, or the row was added blank by hand — and is left for the
    # user to complete through the normal editing UI.
    needs_review = Column(Boolean, nullable=False, default=False)


class LeakSession(Base):
    __tablename__ = "leak_sessions"

    id = Column(Integer, primary_key=True, index=True)
    status = Column(String, nullable=False, default="active")  # "active" | "archived"
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    archived_at = Column(DateTime, nullable=True)


class LeakSubmeterReading(Base):
    __tablename__ = "leak_submeter_readings"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("leak_sessions.id"), nullable=False, index=True)
    mi = Column(String, nullable=False)
    reading = Column(Float, nullable=False)
    record_date = Column(DateTime, nullable=False)
    unit = Column(Integer, nullable=False)  # 0 = gallons, 1 = units of water (CCF)


class LeakMainMeterReading(Base):
    __tablename__ = "leak_main_meter_readings"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("leak_sessions.id"), nullable=False, index=True)
    account_id = Column(String, nullable=True)
    meter_id = Column(String, nullable=True)
    meter_sn = Column(String, nullable=True)
    read_time = Column(DateTime, nullable=False)
    read_value = Column(Float, nullable=False)   # cumulative "Read", in CCF
    flow_time = Column(DateTime, nullable=True)  # period-end date for "Flow"
    flow_value = Column(Float, nullable=True)    # pre-computed period delta from the CSV, in CCF
    register = Column(String, nullable=True)


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
