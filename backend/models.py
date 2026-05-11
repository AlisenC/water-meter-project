from sqlalchemy import Column, Integer, Float, String, DateTime
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
    total_consumption_kl = Column(Float, nullable=False)
    billing_cost_aud = Column(Float, nullable=False)
    source_filename = Column(String, nullable=True)
    imported_at = Column(DateTime, nullable=False)
