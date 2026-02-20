from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .database import database, metadata, engine
from .models import readings
from datetime import datetime
from pydantic import BaseModel

# Create tables if they don't exist
metadata.create_all(engine)

app = FastAPI()

class ReadingCreate(BaseModel):
    household: str
    amount: float

# CORS
origins = ["http://localhost:5173"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup():
    await database.connect()

@app.on_event("shutdown")
async def shutdown():
    await database.disconnect()

# Health endpoint
@app.get("/health")
async def health():
    return {"status": "ok"}

# Add a reading

@app.post("/readings")
async def add_reading(reading: ReadingCreate):
    query = readings.insert().values(
        household=reading.household,
        amount=reading.amount,
        timestamp=datetime.utcnow()
    )

    last_record_id = await database.execute(query)

    return {
        "id": last_record_id,
        "household": reading.household,
        "amount": reading.amount
    }

# Get all readings
@app.get("/readings")
async def get_readings():
    query = readings.select()
    return await database.fetch_all(query)