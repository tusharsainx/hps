"""Batch processing domain models and API schemas."""

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class BatchStatus(str, Enum):
    """Lifecycle status of a bulk processing batch."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    PARTIALLY_FAILED = "partially_failed"
    FAILED = "failed"
    ACTIVATED = "activated"


class RowStatus(str, Enum):
    """Processing status of an individual hospital row."""

    PENDING = "pending"
    CREATING = "creating"
    CREATED = "created"
    FAILED = "failed"
    CREATED_AND_ACTIVATED = "created_and_activated"


class HospitalBatchItem(BaseModel):
    """Individual hospital record summary within a batch result."""

    row: int = Field(..., description="1-indexed row position in the uploaded CSV", ge=1)
    hospital_id: Optional[int] = Field(None, description="Assigned upstream hospital ID (null if failed)")
    name: str = Field(..., description="Hospital name")
    status: str = Field(..., description="Current status of the hospital record")
    error: Optional[str] = Field(None, description="Error reason if the row failed creation")


class BulkProcessResponse(BaseModel):
    """Standard response model for POST /hospitals/bulk as specified by the challenge."""

    batch_id: str = Field(..., description="Unique UUID identifier for this batch")
    total_hospitals: int = Field(..., description="Total number of valid hospital rows submitted")
    processed_hospitals: int = Field(..., description="Number of hospitals successfully processed")
    failed_hospitals: int = Field(..., description="Number of hospitals that failed processing")
    processing_time_seconds: float = Field(..., description="Total execution time in seconds")
    batch_activated: bool = Field(..., description="True if all hospitals were created and batch activated")
    hospitals: List[HospitalBatchItem] = Field(default_factory=list, description="Detailed per-row results")


class BatchProgressResponse(BaseModel):
    """Progress and status model returned by polling and WebSocket endpoints."""

    batch_id: str
    status: BatchStatus
    total_hospitals: int
    processed_hospitals: int
    failed_hospitals: int
    progress_percentage: float = Field(..., ge=0.0, le=100.0)
    batch_activated: bool
    processing_time_seconds: Optional[float] = None
    hospitals: List[HospitalBatchItem] = Field(default_factory=list)


class ValidationErrorItem(BaseModel):
    """Detailed validation issue for a specific CSV row/column."""

    row: Optional[int] = Field(None, description="Row number where the error occurred (null for global)")
    column: Optional[str] = Field(None, description="Column name associated with the error")
    message: str = Field(..., description="Description of the validation failure")


class CsvValidationResponse(BaseModel):
    """Response returned by the CSV pre-validation endpoint."""

    valid: bool
    total_rows: int
    errors: List[ValidationErrorItem] = Field(default_factory=list)
    message: str
