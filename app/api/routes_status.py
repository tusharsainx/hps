"""Status and polling API endpoints."""

from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.models.batch import BatchProgressResponse
from app.services.batch_repository import BaseBatchRepository, get_batch_repository

router = APIRouter(prefix="/hospitals", tags=["Batch Status & Progress"])


@router.get(
    "/bulk/{batch_id}",
    response_model=BatchProgressResponse,
    summary="Get Batch Status & Progress",
    description="Poll current progress, processing status, and row-level breakdown for a batch ID.",
)
async def get_batch_status(
    batch_id: str,
    repo: BaseBatchRepository = Depends(get_batch_repository),
):
    """Retrieve progress status for a specific batch ID."""
    batch = repo.get_batch(batch_id)
    if not batch:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": f"Batch '{batch_id}' not found."},
        )
    return batch.to_progress_response()


@router.get(
    "/bulk",
    response_model=List[BatchProgressResponse],
    summary="List Recent Batches",
    description="List recently submitted bulk processing batches and their statuses.",
)
async def list_batches(
    limit: int = Query(20, ge=1, le=100, description="Max batches to return"),
    repo: BaseBatchRepository = Depends(get_batch_repository),
):
    """List recent batches."""
    return repo.list_recent_batches(limit=limit)
