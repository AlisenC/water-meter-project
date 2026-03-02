from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .database import database, metadata, engine
from .models import readings
from datetime import datetime
from pydantic import BaseModel
from collections import defaultdict
from .ai_agent import router as ai_router

# Create tables if they don't exist
metadata.create_all(engine)

app = FastAPI()

class ReadingCreate(BaseModel):
    household: str
    amount: float

# AI Agent Router
app.include_router(ai_router, prefix="/ai")

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


# Get actual water usage for a household
@app.get("/anomalies")
async def detect_anomalies():
    query = readings.select()
    rows = await database.fetch_all(query)

    # group readings by household
    data = defaultdict(list)

    for r in rows:
        data[r["household"]].append((r["timestamp"], r["amount"]))

    anomalies = []

    for household, values in data.items():
        if len(values) < 3:
            continue

        # sort by timestamp
        values.sort(key=lambda x: x[0])

        prev_usage = values[-2][1] - values[-3][1]
        curr_usage = values[-1][1] - values[-2][1]

        if prev_usage <= 0:
            continue

        pct = ((curr_usage - prev_usage) / prev_usage) * 100

        if pct > 150:
            anomalies.append({
                "household": household,
                "previous_usage": prev_usage,
                "current_usage": curr_usage,
                "increase_percent": round(pct, 2)
            })

    return anomalies