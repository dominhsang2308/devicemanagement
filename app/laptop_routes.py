from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from typing import List, Optional
from app.database import get_session
from app.inventory_models import Laptop, InventoryHistory
from datetime import datetime

router = APIRouter(prefix="/api/inventory/laptops", tags=["laptops"])

@router.get("/", response_model=List[Laptop])
def list_laptops(limit: int = 500, offset: int = 0, session: Session = Depends(get_session)):
    stmt = select(Laptop).limit(limit).offset(offset)
    return session.exec(stmt).all()

@router.get("/{laptop_id}", response_model=Optional[Laptop])
def get_laptop(laptop_id: int, session: Session = Depends(get_session)):
    l = session.get(Laptop, laptop_id)
    if not l:
        raise HTTPException(status_code=404, detail="Laptop not found")
    return l

@router.post("/", status_code=201, response_model=Laptop)
def create_laptop(payload: dict, session: Session = Depends(get_session)):
    try:
        l = Laptop(**payload)
        session.add(l)
        session.commit()
        session.refresh(l)
        session.add(InventoryHistory(action="create_laptop", actor=payload.get("actor"), details=l.dict()))
        session.commit()
        return l
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(e))

@router.patch("/{laptop_id}", response_model=Laptop)
def update_laptop(laptop_id: int, patch: dict, session: Session = Depends(get_session)):
    l = session.get(Laptop, laptop_id)
    if not l:
        raise HTTPException(status_code=404, detail="Laptop not found")
    for k, v in patch.items():
        if hasattr(l, k):
            setattr(l, k, v)
    l.updated_at = datetime.utcnow()
    session.add(l)
    session.add(InventoryHistory(action="update_laptop", actor=patch.get("actor"), details={"id": laptop_id, "patch": patch}))
    session.commit()
    session.refresh(l)
    return l

@router.delete("/{laptop_id}", status_code=204)
def delete_laptop(laptop_id: int, session: Session = Depends(get_session)):
    l = session.get(Laptop, laptop_id)
    if not l:
        raise HTTPException(status_code=404, detail="Laptop not found")
    session.delete(l)
    session.add(InventoryHistory(action="delete_laptop", actor="api", details={"id": laptop_id}))
    session.commit()
    return {}