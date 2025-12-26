from sqlmodel import Session
from sqlalchemy.exc import SQLAlchemyError
from .inventory_models import InventoryItem, LicensePool, Assignment, InventoryHistory
from datetime import datetime
from typing import Optional
import time

def create_inventory_item(session: Session, payload: dict, actor: Optional[str] = None) -> InventoryItem:
    item = InventoryItem(**payload)
    session.add(item)
    session.commit()
    session.refresh(item)
    session.add(InventoryHistory(action="create_item", actor=actor, details=item.dict()))
    session.commit()
    return item

def update_inventory_item(session: Session, item_id: int, patch: dict, actor: Optional[str] = None) -> InventoryItem:
    item = session.get(InventoryItem, item_id)
    if not item:
        raise ValueError("Item not found")
    for k, v in patch.items():
        if hasattr(item, k):
            setattr(item, k, v)
    item.updated_at = datetime.utcnow()
    item.version = (item.version or 1) + 1
    session.add(item)
    session.add(InventoryHistory(action="update_item", actor=actor, details={"id": item_id, "patch": patch}))
    session.commit()
    session.refresh(item)
    return item

def delete_inventory_item(session: Session, item_id: int, actor: Optional[str] = None) -> None:
    item = session.get(InventoryItem, item_id)
    if not item:
        raise ValueError("Item not found")
    session.delete(item)
    session.add(InventoryHistory(action="delete_item", actor=actor, details={"id": item_id}))
    session.commit()

def create_license_pool(session: Session, payload: dict, actor: Optional[str] = None) -> LicensePool:
    lp = LicensePool(**payload)
    session.add(lp)
    session.commit()
    session.refresh(lp)
    session.add(InventoryHistory(action="create_licensepool", actor=actor, details=lp.dict()))
    session.commit()
    return lp

def allocate_license(session: Session, license_id: int, user_upn: str, device_graph_id: Optional[str], actor: str, max_retries: int = 3) -> Assignment:
    """
    Atomically increment LicensePool. For Postgres, use SELECT ... FOR UPDATE (can be added later).
    For SQLite we use simple retry on SQLAlchemyError.
    """
    for attempt in range(max_retries):
        try:
            lp = session.get(LicensePool, license_id)
            if not lp:
                raise ValueError("License pool not found")
            available = lp.total - lp.allocated
            if available <= 0:
                raise ValueError("No available license")
            lp.allocated += 1
            session.add(lp)
            assignment = Assignment(license_id=license_id, user_upn=user_upn, device_graph_id=device_graph_id, assigned_by=actor)
            session.add(assignment)
            session.add(InventoryHistory(action="allocate_license", actor=actor, details={
                "license_id": license_id, "user_upn": user_upn, "device_graph_id": device_graph_id
            }))
            session.commit()
            session.refresh(assignment)
            session.refresh(lp)
            return assignment
        except SQLAlchemyError:
            session.rollback()
            if attempt < max_retries - 1:
                time.sleep(0.1 * (attempt + 1))
                continue
            raise

def return_license(session: Session, assignment_id: int, actor: str) -> Assignment:
    a = session.get(Assignment, assignment_id)
    if not a:
        raise ValueError("Assignment not found")
    if a.status != "assigned":
        raise ValueError("Assignment not in assigned state")
    lp = session.get(LicensePool, a.license_id) if a.license_id else None
    a.status = "returned"
    session.add(a)
    if lp:
        lp.allocated = max(0, lp.allocated - 1)
        session.add(lp)
    session.add(InventoryHistory(action="return_license", actor=actor, details={"assignment_id": assignment_id}))
    session.commit()
    session.refresh(a)
    if lp:
        session.refresh(lp)
    return a

def create_assignment_for_item(session: Session, item_id: int, device_graph_id: Optional[str], user_upn: Optional[str], actor: str) -> Assignment:
    """
    Assign a physical inventory item (e.g., a laptop) to a device/user.
    This does not touch license pools; it records Assignment with item_id field.
    """
    assignment = Assignment(item_id=item_id, device_graph_id=device_graph_id, user_upn=user_upn, assigned_by=actor)
    session.add(assignment)
    session.add(InventoryHistory(action="assign_item", actor=actor, details={"item_id": item_id, "user_upn": user_upn, "device_graph_id": device_graph_id}))
    session.commit()
    session.refresh(assignment)
    return assignment