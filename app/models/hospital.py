"""Hospital domain models and schemas."""

from typing import Optional
from pydantic import BaseModel, Field


class HospitalRecord(BaseModel):
    """Represents a validated hospital row parsed from an input CSV."""

    row: int = Field(..., description="1-indexed row position in the source CSV file", ge=1)
    name: str = Field(..., min_length=1, description="Official name of the hospital")
    address: str = Field(..., min_length=1, description="Physical address of the hospital")
    phone: Optional[str] = Field(None, description="Optional contact telephone number")


class HospitalCreate(BaseModel):
    """Payload sent to upstream Hospital Directory API."""

    name: str = Field(..., min_length=1)
    address: str = Field(..., min_length=1)
    phone: Optional[str] = None
    creation_batch_id: Optional[str] = None


class HospitalResponse(BaseModel):
    """Hospital record as returned by the Hospital Directory API."""

    id: int
    name: str
    address: str
    phone: Optional[str] = None
    creation_batch_id: Optional[str] = None
    active: bool = False
    created_at: Optional[str] = None
