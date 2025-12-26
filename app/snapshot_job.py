# app/snapshot_job.py
from sqlmodel import Session
from .database import get_engine
from .ms_graph import fetch_managed_devices
from .summary_utils import summarize_devices
from .models import DeviceSnapshot
from datetime import datetime

def run_snapshot_once():
    devices = fetch_managed_devices()  # list of device dicts from Graph
    s = summarize_devices(devices)     # returns aggregated dict
    snap = DeviceSnapshot(
        timestamp=datetime.utcnow(),
        total=s["total"],
        corporate=s["corporate"],
        personal=s["personal"],
        compliant=s["compliant"],
        noncompliant=s["noncompliant"],
        by_os=s.get("by_os", {}),
        by_os_version=s.get("by_os_version", {}),
        raw_sample={"count": min(5, len(devices)), "examples": devices[:5]},
    )
    engine = get_engine()
    with Session(engine) as session:
        session.add(snap)
        session.commit()
    return snap