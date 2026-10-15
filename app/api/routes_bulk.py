"""Bulk processing API endpoints."""

import logging
from typing import Optional
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    Query,
    UploadFile,
    status,
)

from app.config import Settings, get_settings
from app.models.batch import (
    BatchProgressResponse,
    BulkProcessResponse,
    CsvValidationResponse,
)
from app.services.csv_validator import CsvValidator, CsvValidationException
from app.services.bulk_processor import BulkProcessor
from app.services.batch_repository import get_batch_repository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/hospitals", tags=["Bulk Processing"])


def get_bulk_processor(
    settings: Settings = Depends(get_settings),
) -> BulkProcessor:
    """Dependency injector for BulkProcessor."""
    return BulkProcessor(settings=settings)


@router.post(
    "/bulk",
    response_model=BulkProcessResponse,
    status_code=status.HTTP_200_OK,
    summary="Bulk Create Hospitals from CSV",
    description=(
        "Upload a multipart CSV file containing hospital records (name, address, phone). "
        "Creates each hospital in the upstream directory API with a unique batch ID, "
        "and activates the batch once all records are successfully created."
    ),
)
async def bulk_create_hospitals(
    file: UploadFile = File(..., description="CSV file with columns: name,address,phone"),
    background: bool = Query(
        False,
        description="If true, returns 202 immediately and processes batch in the background.",
    ),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    settings: Settings = Depends(get_settings),
    processor: BulkProcessor = Depends(get_bulk_processor),
):
    """Bulk create hospitals from CSV upload."""
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": "Invalid file type. Please upload a file with a .csv extension.",
                "filename": file.filename,
            },
        )

    # Read uploaded file contents directly into memory
    content_bytes = await file.read()

    # Validate CSV content and enforce max rows (<= 20)
    validator = CsvValidator(max_rows=settings.MAX_CSV_ROWS)
    try:
        records = validator.validate_and_parse(content_bytes)
    except CsvValidationException as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": exc.message,
                "errors": [err.model_dump() for err in exc.errors],
            },
        )

    if background:
        # Background mode: initialize batch and process asynchronously
        import uuid
        batch_id = str(uuid.uuid4())
        repo = get_batch_repository()
        batch = repo.create_batch(batch_id, records)
        background_tasks.add_task(processor.process_batch, records, batch_id)
        return batch.to_bulk_response()

    # Synchronous mode (Standard requirement): wait for full execution
    try:
        response = await processor.process_batch(records)
        return response
    except Exception as exc:
        logger.exception("Bulk processing pipeline encountered an unexpected error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": f"Internal processing error: {str(exc)}"},
        )


@router.post(
    "/bulk/validate",
    response_model=CsvValidationResponse,
    status_code=status.HTTP_200_OK,
    summary="Pre-validate CSV Format",
    description="Validate CSV formatting, headers, required values, and row limits without creating records.",
)
async def validate_csv_file(
    file: UploadFile = File(..., description="CSV file to validate"),
    settings: Settings = Depends(get_settings),
):
    """Bonus feature: Validate CSV format before executing bulk operations."""
    content_bytes = await file.read()
    validator = CsvValidator(max_rows=settings.MAX_CSV_ROWS)
    return validator.check_csv(content_bytes)


@router.post(
    "/bulk/{batch_id}/resume",
    response_model=BulkProcessResponse,
    status_code=status.HTTP_200_OK,
    summary="Resume Failed Bulk Operation",
    description="Resume a previously failed or partially processed bulk batch.",
)
async def resume_bulk_batch(
    batch_id: str,
    processor: BulkProcessor = Depends(get_bulk_processor),
):
    """Bonus feature: Resume a failed bulk operation."""
    try:
        return await processor.resume_batch(batch_id)
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": f"Batch ID '{batch_id}' was not found in the active repository."},
        )
    except Exception as exc:
        logger.exception("Failed to resume batch %s: %s", batch_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": f"Resume failed: {str(exc)}"},
        )


@router.delete(
    "/bulk/{batch_id}",
    summary="Delete/Rollback Batch",
    description="Roll back all created hospitals for the given batch ID from the upstream directory.",
)
async def delete_bulk_batch(
    batch_id: str,
    processor: BulkProcessor = Depends(get_bulk_processor),
):
    """Delete all hospitals in batch upstream."""
    try:
        result = await processor.delete_batch(batch_id)
        return result
    except Exception as exc:
        logger.error("Failed to delete batch %s: %s", batch_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": f"Batch rollback failed: {str(exc)}"},
        )
