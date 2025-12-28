from sqlmodel import Session, select
from sqlalchemy.exc import SQLAlchemyError
from .inventory_models import InventoryItem, LicensePool, Assignment, InventoryHistory, Laptop
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
    This records Assignment with item_id field and writes history.
    """
    # verify the item exists
    item = session.get(InventoryItem, item_id)
    if not item:
        raise ValueError("Item not found")

    # create the assignment
    assignment = Assignment(item_id=item_id, device_graph_id=device_graph_id, user_upn=user_upn, assigned_by=actor)
    session.add(assignment)

    # if there's a Laptop record linked to this item, update its status and assigned fields
    laptop = session.exec(select(Laptop).where(Laptop.item_id == item_id)).first()
    if laptop:
        if laptop.status == "in_use":
            raise ValueError("Device already assigned")
        laptop.status = "in_use"
        laptop.assigned_to_upn = user_upn
        if device_graph_id:
            laptop.device_graph_id = device_graph_id
        laptop.updated_at = datetime.utcnow()
        session.add(laptop)

    session.add(InventoryHistory(action="assign_item", actor=actor, details={"item_id": item_id, "user_upn": user_upn, "device_graph_id": device_graph_id}))
    session.commit()
    session.refresh(assignment)
    if laptop:
        session.refresh(laptop)
    return assignment

def return_assignment(session: Session, assignment_id: int, actor: str) -> Assignment:
    """
    Return an assignment (either a license assignment or an item assignment).
    Updates assignment.status and any related LicensePool or Laptop state.
    """
    a = session.get(Assignment, assignment_id)
    if not a:
        raise ValueError("Assignment not found")
    if a.status != "assigned":
        raise ValueError("Assignment not in assigned state")

    # Handle license return
    if a.license_id:
        lp = session.get(LicensePool, a.license_id) if a.license_id else None
        a.status = "returned"
        session.add(a)
        if lp:
            lp.allocated = max(0, lp.allocated - 1)
            lp.updated_at = datetime.utcnow()
            session.add(lp)
    # Handle physical item return
    elif a.item_id:
        laptop = session.exec(select(Laptop).where(Laptop.item_id == a.item_id)).first()
        a.status = "returned"
        session.add(a)
        if laptop:
            laptop.status = "in_stock"
            laptop.assigned_to_upn = None
            laptop.device_graph_id = None
            laptop.updated_at = datetime.utcnow()
            session.add(laptop)
    else:
        # unknown assignment type, still mark returned
        a.status = "returned"
        session.add(a)

    session.add(InventoryHistory(action="return_assignment", actor=actor, details={"assignment_id": assignment_id}))
    session.commit()
    session.refresh(a)
    return a

def return_assignment_by_item(session: Session, item_id: int, actor: str) -> Assignment:
    """
    Find the active assignment for the given item_id and return it (check-in).
    Raises ValueError if no active assignment found.
    """
    stmt = select(Assignment).where(Assignment.item_id == item_id, Assignment.status == "assigned")
    a = session.exec(stmt).first()
    if not a:
        raise ValueError("No active assignment for item")
    return return_assignment(session, a.id, actor)

def create_device_atomic(session: Session, item_payload: dict, laptop_payload: dict, actor: Optional[str] = None):
    """
    Create InventoryItem and Laptop in single transaction (atomic).
    Returns {"item": InventoryItem, "laptop": Laptop}
    """
    try:
        item = InventoryItem(**item_payload)
        session.add(item)
        session.flush()  # ensure id assigned
        # link item_id to laptop payload if not provided
        laptop_payload = dict(laptop_payload)
        if not laptop_payload.get("item_id"):
            laptop_payload["item_id"] = item.id
        laptop = Laptop(**laptop_payload)
        session.add(laptop)
        session.add(InventoryHistory(action="create_device", actor=actor, details={"item": item_payload, "laptop": laptop_payload}))
        session.commit()
        session.refresh(item)
        session.refresh(laptop)
        return {"item": item, "laptop": laptop}
    except Exception:
        session.rollback()
        raise