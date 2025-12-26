from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from typing import List
from .database import get_session
from .inventory_models import InventoryItem, LicensePool, Assignment, InventoryHistory
from .inventory_crud import (
    create_inventory_item, update_inventory_item, delete_inventory_item,
    create_license_pool, allocate_license, return_license, create_assignment_for_item
)

router = APIRouter(prefix="/api/inventory", tags=["inventory"])

# Inventory items CRUD
@router.get("/", response_model=List[InventoryItem])
def list_items(limit: int = 500, offset: int = 0, session: Session = Depends(get_session)):
    stmt = select(InventoryItem).limit(limit).offset(offset)
    return session.exec(stmt).all()

@router.post("/", status_code=201)
def api_create_item(payload: dict, session: Session = Depends(get_session)):
    try:
        item = create_inventory_item(session, payload, actor=payload.get("actor"))
        return item
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.patch("/{item_id}")
def api_update_item(item_id: int, patch: dict, session: Session = Depends(get_session)):
    try:
        item = update_inventory_item(session, item_id, patch, actor=patch.get("actor"))
        return item
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.delete("/{item_id}", status_code=204)
def api_delete_item(item_id: int, session: Session = Depends(get_session)):
    try:
        delete_inventory_item(session, item_id, actor="api")
        return {}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# License pools
@router.get("/licenses", response_model=List[LicensePool])
def list_licenses(session: Session = Depends(get_session)):
    stmt = select(LicensePool)
    return session.exec(stmt).all()

@router.post("/licenses", status_code=201)
def create_license_pool_endpoint(payload: dict, session: Session = Depends(get_session)):
    try:
        lp = create_license_pool(session, payload, actor=payload.get("actor"))
        return lp
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/licenses/{license_id}/allocate")
def api_allocate_license(license_id: int, body: dict, session: Session = Depends(get_session)):
    user_upn = body.get("user_upn")
    device_graph_id = body.get("device_graph_id")
    actor = body.get("actor", "unknown")
    try:
        assignment = allocate_license(session, license_id, user_upn, device_graph_id, actor)
        return assignment
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# Assign physical item (e.g., laptop) endpoint
@router.post("/assign", status_code=201)
def api_assign_item(body: dict, session: Session = Depends(get_session)):
    item_id = body.get("item_id")
    device_graph_id = body.get("device_graph_id")
    user_upn = body.get("user_upn")
    actor = body.get("actor", "unknown")
    if not item_id:
        raise HTTPException(status_code=400, detail="item_id required")
    try:
        assignment = create_assignment_for_item(session, item_id, device_graph_id, user_upn, actor)
        return assignment
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/assignments/{assignment_id}/return")
def api_return_assignment(assignment_id: int, body: dict, session: Session = Depends(get_session)):
    actor = body.get("actor", "unknown")
    try:
        a = return_license(session, assignment_id, actor)
        return a
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# History / audit
@router.get("/history", response_model=List[InventoryHistory])
def get_history(limit: int = 500, session: Session = Depends(get_session)):
    stmt = select(InventoryHistory).order_by(InventoryHistory.timestamp.desc()).limit(limit)
    return session.exec(stmt).all()

# Bulk import
@router.post("/bulk_import")
def bulk_import(payload: dict, session: Session = Depends(get_session)):
    items = payload.get("items") or []
    if not items:
        raise HTTPException(status_code=400, detail="No items")
    imported = 0
    for rec in items:
        try:
            item = InventoryItem(**rec)
            session.add(item)
            session.add(InventoryHistory(action="bulk_import", actor=rec.get("actor", "bulk"), details=rec))
            imported += 1
        except Exception as e:
            session.rollback()
            raise HTTPException(status_code=400, detail=f"Error importing record: {e}")
    session.commit()
    return {"imported": imported}