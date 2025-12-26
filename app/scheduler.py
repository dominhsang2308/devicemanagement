from apscheduler.schedulers.background import BackgroundScheduler
from .snapshot_job import run_snapshot_once
from datetime import datetime

scheduler = BackgroundScheduler()
def start_scheduler(interval_minutes: int = 15):
    try:
        scheduler.remove_all_jobs()
    except Exception:
        pass
    scheduler.add_job(run_snapshot_once, "interval", minutes=interval_minutes, id="snapshot_job")
    scheduler.start()

