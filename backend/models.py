from sqlalchemy import Column, Integer, Float, String, DateTime
from .database import Base

class Reading(Base):
    __tablename__ = "readings"

    id = Column(Integer, primary_key=True, index=True)
    mi = Column(String)
    reading = Column(Float)
    record_date = Column(DateTime)
    unit = Column(Integer)
