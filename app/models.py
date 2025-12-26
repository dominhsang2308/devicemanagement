from sqlmodel import SQLModel, Field, Column
from datetime import datetime
from typing import Optional
from sqlalchemy import JSON

class DeviceSnapshot(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    timestamp: datetime = Field(default_factory=datetime.utcnow, index=True)
    total: int = 0
    corporate: int = 0
    personal: int = 0
    compliant: int = 0
    noncompliant: int = 0
    by_os : Optional[dict] = Field(default_factory=dict, sa_column=Column(JSON))
    by_os_version: Optional[dict] = Field(default_factory=dict, sa_column=Column(JSON))
    raw_sample: Optional[dict] = Field(default_factory=dict, sa_column=Column(JSON))