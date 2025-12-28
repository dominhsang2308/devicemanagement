from typing import Optional, Dict
from enum import Enum
from sqlmodel import SQLModel, Field, Column
from datetime import datetime
from sqlalchemy import JSON, Integer

class InventoryItem(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    sku: str = Field(index=True, nullable=False)
    name: str
    item_type: Optional[str] = Field(default="device")  # device | accessory | license
    quantity: int = Field(default=0)
    location: Optional[str] = None
    metadata_: Optional[Dict] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    version: int = Field(default=1, sa_column=Column(Integer, nullable=False))

class LicensePool(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    sku: str = Field(index=True, nullable=False, unique=True)
    display_name: Optional[str] = None
    total: int = Field(default=0)
    allocated: int = Field(default=0)
    metadata_: Optional[Dict] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

class Assignment(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    item_id: Optional[int] = Field(default=None, foreign_key="inventoryitem.id", index=True)
    license_id: Optional[int] = Field(default=None, foreign_key="licensepool.id", index=True)
    device_graph_id: Optional[str] = Field(default=None, index=True)
    user_upn: Optional[str] = Field(default=None, index=True)
    assigned_by: Optional[str] = None
    assigned_at: datetime = Field(default_factory=datetime.utcnow)
    status: str = Field(default="assigned")  # assigned | returned | revoked
    notes: Optional[str] = None

class InventoryHistory(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    action: str  # create/update/allocate/return/delete/bulk_import
    actor: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    details: Optional[Dict] = Field(default_factory=dict, sa_column=Column(JSON))

# -------------------------
# DeviceType Enum (chooses device category)
# -------------------------
class DeviceType(str, Enum):
    LAPTOP = "Laptop"
    MONITOR = "Monitor"
    PHONE = "Phone"
    TABLET = "Tablet"
    ACCESSORY = "Accessory"
    OTHER = "Other"

# -------------------------
# New: Laptop specific model (with device_type)
# -------------------------
class Laptop(SQLModel, table=True):
    """
    Laptop record with detailed fields for TEC team.
    - device_type: categorization (Laptop, Monitor, Phone, ...)
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    item_id: Optional[int] = Field(default=None, foreign_key="inventoryitem.id", index=True, nullable=True)
    device_type: DeviceType = Field(default=DeviceType.LAPTOP)
    company: Optional[str] = None
    asset_tag: Optional[str] = Field(default=None, index=True)
    serial: Optional[str] = Field(default=None, index=True)
    model: Optional[str] = None
    status: str = Field(default="in_stock", description="in_stock | assigned | reserved | retired")
    assigned_to_upn: Optional[str] = Field(default=None, index=True)
    assigned_to_id: Optional[str] = Field(default=None, index=True)
    os: Optional[str] = None
    device_graph_id: Optional[str] = Field(default=None, index=True)  # optional link to Intune managedDevice id
    notes: Optional[Dict] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)