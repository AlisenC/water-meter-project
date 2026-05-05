from fastapi import FastAPI, UploadFile, File
import csv
from io import StringIO
from fastapi.middleware.cors import CORSMiddleware
from .database import SessionLocal, engine
from .models import Base, Reading
from datetime import datetime
from pydantic import BaseModel
from collections import defaultdict
from .ai_agent import router as ai_router

# Create tables if they don't exist
Base.metadata.create_all(bind=engine)
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

# Health endpoint
@app.get("/health")
async def health():
    return {"status": "ok"}

# Add a reading
@app.post("/readings")
async def add_reading(reading: ReadingCreate):
    db = SessionLocal()

    new_reading = Reading(
        mi=reading.household,
        reading=reading.amount,
        record_date=datetime.utcnow(),
        unit=1
    )

    db.add(new_reading)
    db.commit()
    db.refresh(new_reading)
    db.close()

    return new_reading

# Get all readings
@app.get("/readings")
async def get_readings():
    db = SessionLocal()
    readings = db.query(Reading).all()
    db.close()
    return readings

# Import CSV
@app.post("/import-csv")
async def import_csv(file: UploadFile = File(...)):
    db = SessionLocal()

    contents = await file.read()
    csv_text = contents.decode("utf-8")

    reader = csv.DictReader(StringIO(csv_text), delimiter=",")

    inserted = 0

    for row in reader:
        try:
            parsed_date = datetime.strptime(row["record_date"], "%Y-%m-%d")

            reading = Reading(
                mi=row["mi"],
                reading=float(row["reading"]),
                record_date=parsed_date,
                unit=int(row["unit"])
            )

            db.add(reading)
            inserted += 1

        except Exception as e:
            print("Skipping row:", row, e)

    db.commit()
    db.close()

    return {"message": f"{inserted} rows imported successfully"}

# Delete a reading
@app.delete("/readings/{reading_id}")
async def delete_reading(reading_id: int):
    db = SessionLocal()
    reading = db.query(Reading).filter(Reading.id == reading_id).first()
    if not reading:
        db.close()
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Reading not found")
    db.delete(reading)
    db.commit()
    db.close()
    return {"ok": True}

# Detect anomalies in usage
@app.get("/anomalies")
async def detect_anomalies():
    db = SessionLocal()
    rows = db.query(Reading).all()
    db.close()

    data = defaultdict(list)

    for r in rows:
        data[r.mi].append((r.record_date, r.reading))

    anomalies = []

    for household, values in data.items():
        if len(values) < 3:
            continue

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
