from fastapi import FastAPI, UploadFile, File
import csv
from io import StringIO
from fastapi.middleware.cors import CORSMiddleware
from .database import SessionLocal, engine
from .models import Base, Reading
from datetime import datetime
from pydantic import BaseModel

# Create tables if they don't exist
Base.metadata.create_all(bind=engine)
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

# Import data from CSV File
@app.post("/import-csv")
async def import_csv(file: UploadFile = File(...)):
    db = SessionLocal()

    contents = await file.read()
    csv_text = contents.decode("utf-8")
    reader = csv.DictReader(StringIO(csv_text), delimiter=",")  # <-- fix here

    inserted = 0

    for row in reader:
        try:
            parsed_date = datetime.strptime(row["record_date"], "%Y-%m-%d")  # adjust format if needed

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
