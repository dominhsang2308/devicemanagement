from fastapi import FastAPI, BackgroundTasks, Depends
from sqlmodel import Session, select
from dotenv import load_dotenv
from .ms_graph import fetch_managed_devices
from .summary_utils import summarize_devices
from .database import create_db_and_tables, get_engine
from .models import DeviceSnapshot
from sqlalchemy.orm import sessionmaker
from .scheduler import start_scheduler
from .snapshot_job import run_snapshot_once
from app.inventory_routes import router as inventory_router
from app.users_routes import router as users_router
load_dotenv()

app = FastAPI(title="Device Management Summary API")
app.include_router(inventory_router)
app.include_router(users_router)
@app.on_event("startup")
def on_startup():
    create_db_and_tables()
    start_scheduler(interval_minutes=15)

@app.get("/api/dashboard/summary")
def dashboard_summary():
    devices = fetch_managed_devices()
    summary = summarize_devices(devices)
    return summary


@app.post("/api/dashboard/snapshot")
def create_snapshot(background_tasks: BackgroundTasks):
    background_tasks.add_task(run_snapshot_once)
    return {"status" : "snapshot_scheduled"}

@app.get("/api/dashboard/snapshots")
def get_snapshot(limit:int = 100):
    engine = get_engine()
    with Session(engine) as session:
        statement = select(DeviceSnapshot).order_by(DeviceSnapshot.timestamp.desc()).limit(limit)
        rows = session.exec(statement).all()

        return rows