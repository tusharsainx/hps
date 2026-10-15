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

    batch_id: str = Field(..., description="Unique UUID identifier for this batch", examples=["550e8400-e29b-41d4-a716-446655440000"])
    total_hospitals: int = Field(..., description="Total number of valid hospital rows submitted", examples=[20])
    processed_hospitals: int = Field(..., description="Number of hospitals successfully processed", examples=[20])
    failed_hospitals: int = Field(..., description="Number of hospitals that failed processing", examples=[0])
    processing_time_seconds: float = Field(..., description="Total execution time in seconds", examples=[0.85])
    batch_activated: bool = Field(..., description="True if all hospitals were created and batch activated", examples=[True])
    hospitals: List[HospitalBatchItem] = Field(default_factory=list, description="Detailed per-row results")

    model_config = {
        "json_schema_extra": {
            "example": {
                "batch_id": "550e8400-e29b-41d4-a716-446655440000",
                "total_hospitals": 2,
                "processed_hospitals": 2,
                "failed_hospitals": 0,
                "processing_time_seconds": 0.85,
                "batch_activated": True,
                "hospitals": [
                    {
                        "row": 1,
                        "hospital_id": 101,
                        "name": "General Hospital",
                        "status": "created_and_activated",
                        "error": None,
                    },
                    {
                        "row": 2,
                        "hospital_id": 102,
                        "name": "St. Jude Children's Research Hospital",
                        "status": "created_and_activated",
                        "error": None,
                    },
                ],
            }
        }
    }


class BatchProgressResponse(BaseModel):
    """Progress and status model returned by polling and WebSocket endpoints."""

    batch_id: str = Field(..., examples=["550e8400-e29b-41d4-a716-446655440000"])
    status: BatchStatus = Field(..., examples=[BatchStatus.ACTIVATED])
    total_hospitals: int = Field(..., examples=[20])
    processed_hospitals: int = Field(..., examples=[20])
    failed_hospitals: int = Field(..., examples=[0])
    progress_percentage: float = Field(..., ge=0.0, le=100.0, examples=[100.0])
    batch_activated: bool = Field(..., examples=[True])
    processing_time_seconds: Optional[float] = Field(None, examples=[0.85])
    hospitals: List[HospitalBatchItem] = Field(default_factory=list)

    model_config = {
        "json_schema_extra": {
            "example": {
                "batch_id": "550e8400-e29b-41d4-a716-446655440000",
                "status": "activated",
                "total_hospitals": 20,
                "processed_hospitals": 20,
                "failed_hospitals": 0,
                "progress_percentage": 100.0,
                "batch_activated": True,
                "processing_time_seconds": 0.85,
                "hospitals": [],
            }
        }
    }


class ValidationErrorItem(BaseModel):
    """Detailed validation issue for a specific CSV row/column."""

    row: Optional[int] = Field(None, description="Row number where the error occurred (null for global)", examples=[2])
    column: Optional[str] = Field(None, description="Column name associated with the error", examples=["name"])
    message: str = Field(..., description="Description of the validation failure", examples=["Row 2: 'name' is required and cannot be empty."])


class CsvValidationResponse(BaseModel):
    """Response returned by the CSV pre-validation endpoint."""

    valid: bool = Field(..., examples=[True])
    total_rows: int = Field(..., examples=[20])
    errors: List[ValidationErrorItem] = Field(default_factory=list)
    message: str = Field(..., examples=["Validation successful. 20 valid hospital record(s) ready for processing."])
