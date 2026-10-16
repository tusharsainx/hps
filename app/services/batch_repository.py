"""Batch state storage and repository layer."""

from abc import ABC, abstractmethod
from collections import OrderedDict
import threading
import time
from typing import Dict, List, Optional

from app.models.batch import (
    BatchStatus,
    BatchProgressResponse,
    BulkProcessResponse,
    HospitalBatchItem,
)
from app.models.hospital import HospitalRecord


class BatchRecordInternal:
    """Internal representation of a batch state."""

    def __init__(self, batch_id: str, total_hospitals: int):
        self.batch_id = batch_id
        self.total_hospitals = total_hospitals
        self.processed_hospitals = 0
        self.failed_hospitals = 0
        self.status = BatchStatus.PENDING
        self.batch_activated = False
        self.start_time = time.time()
        self.end_time: Optional[float] = None
        self.processing_time_seconds = 0.0

        # Mappings by 1-indexed row number
        self.hospitals: Dict[int, HospitalBatchItem] = {}
        self.source_records: Dict[int, HospitalRecord] = {}

    def calculate_elapsed(self) -> float:
        """Calculate elapsed processing time."""
        if self.end_time:
            return round(self.end_time - self.start_time, 2)
        return round(time.time() - self.start_time, 2)

    def sync_counters(self):
        """Ensure processed and failed counters match actual row statuses."""
        self.processed_hospitals = sum(
            1 for h in self.hospitals.values() if h.status in ("created", "created_and_activated")
        )
        self.failed_hospitals = sum(
            1 for h in self.hospitals.values() if h.status == "failed"
        )

    def to_bulk_response(self) -> BulkProcessResponse:
        """Export state in the exact response format required by the specification."""
        self.sync_counters()
        items = [self.hospitals[r] for r in sorted(self.hospitals.keys())]
        return BulkProcessResponse(
            batch_id=self.batch_id,
            total_hospitals=self.total_hospitals,
            processed_hospitals=self.processed_hospitals,
            failed_hospitals=self.failed_hospitals,
            processing_time_seconds=self.processing_time_seconds or self.calculate_elapsed(),
            batch_activated=self.batch_activated,
            hospitals=items,
        )

    def to_progress_response(self) -> BatchProgressResponse:
        """Export state for progress polling endpoints."""
        self.sync_counters()
        items = [self.hospitals[r] for r in sorted(self.hospitals.keys())]
        completed = self.processed_hospitals + self.failed_hospitals
        pct = round((completed / self.total_hospitals * 100.0) if self.total_hospitals > 0 else 0.0, 1)

        return BatchProgressResponse(
            batch_id=self.batch_id,
            status=self.status,
            total_hospitals=self.total_hospitals,
            processed_hospitals=self.processed_hospitals,
            failed_hospitals=self.failed_hospitals,
            progress_percentage=min(100.0, pct),
            batch_activated=self.batch_activated,
            processing_time_seconds=self.calculate_elapsed(),
            hospitals=items,
        )


class BaseBatchRepository(ABC):
    """Abstract interface defining storage operations for bulk batches.
    
    Allows transparent swapping between in-memory storage (Standard Scale)
    and Redis / PostgreSQL (Enterprise Scale).
    """

    @abstractmethod
    def create_batch(self, batch_id: str, records: List[HospitalRecord]) -> BatchRecordInternal:
        """Initialize a new batch."""

    @abstractmethod
    def get_batch(self, batch_id: str) -> Optional[BatchRecordInternal]:
        """Retrieve batch state by ID."""

    @abstractmethod
    def update_row_success(self, batch_id: str, row: int, hospital_id: int):
        """Record successful creation of a hospital row."""

    @abstractmethod
    def update_row_failure(self, batch_id: str, row: int, error_message: str):
        """Record failure of a hospital row."""

    @abstractmethod
    def complete_batch(self, batch_id: str, activated: bool):
        """Mark batch processing finished and record completion time."""

    @abstractmethod
    def list_recent_batches(self, limit: int = 50) -> List[BatchProgressResponse]:
        """List recently processed batches."""


class InMemoryBatchRepository(BaseBatchRepository):
    """Thread-safe in-memory batch repository with bounded LRU eviction and TTL cleanup."""

    def __init__(self, max_capacity: int = 10000, ttl_seconds: int = 86400):
        self._lock = threading.Lock()
        self._store: OrderedDict[str, BatchRecordInternal] = OrderedDict()
        self.max_capacity = max_capacity
        self.ttl_seconds = ttl_seconds

    def _evict_expired_or_overflow(self):
        """Evict batches older than ttl_seconds and enforce bounded capacity."""
        now = time.time()
        # 1. Prune expired batches older than TTL (ignoring batches still actively processing)
        if self.ttl_seconds > 0:
            expired_keys = [
                k for k, b in self._store.items()
                if (now - b.start_time) > self.ttl_seconds and b.status != BatchStatus.PROCESSING
            ]
            for k in expired_keys:
                self._store.pop(k, None)

        # 2. Enforce LRU eviction if capacity is reached
        while len(self._store) >= self.max_capacity:
            self._store.popitem(last=False)

    def create_batch(self, batch_id: str, records: List[HospitalRecord]) -> BatchRecordInternal:
        with self._lock:
            self._evict_expired_or_overflow()

            batch = BatchRecordInternal(batch_id=batch_id, total_hospitals=len(records))
            batch.status = BatchStatus.PROCESSING

            for rec in records:
                batch.source_records[rec.row] = rec
                batch.hospitals[rec.row] = HospitalBatchItem(
                    row=rec.row,
                    hospital_id=None,
                    name=rec.name,
                    status="pending",
                    error=None,
                )

            self._store[batch_id] = batch
            return batch

    def get_batch(self, batch_id: str) -> Optional[BatchRecordInternal]:
        with self._lock:
            return self._store.get(batch_id)

    def update_row_success(self, batch_id: str, row: int, hospital_id: int):
        with self._lock:
            batch = self._store.get(batch_id)
            if not batch:
                return
            if row in batch.hospitals:
                batch.hospitals[row].hospital_id = hospital_id
                batch.hospitals[row].status = "created"
                batch.hospitals[row].error = None
                batch.sync_counters()

    def update_row_failure(self, batch_id: str, row: int, error_message: str):
        with self._lock:
            batch = self._store.get(batch_id)
            if not batch:
                return
            if row in batch.hospitals:
                batch.hospitals[row].status = "failed"
                batch.hospitals[row].error = error_message
                batch.sync_counters()

    def complete_batch(self, batch_id: str, activated: bool):
        with self._lock:
            batch = self._store.get(batch_id)
            if not batch:
                return
            batch.end_time = time.time()
            batch.processing_time_seconds = round(batch.end_time - batch.start_time, 2)
            batch.batch_activated = activated

            if activated:
                batch.status = BatchStatus.ACTIVATED
                # Update status of successfully created items
                for item in batch.hospitals.values():
                    if item.status == "created":
                        item.status = "created_and_activated"
            elif batch.failed_hospitals > 0:
                batch.status = (
                    BatchStatus.PARTIALLY_FAILED
                    if batch.processed_hospitals > 0
                    else BatchStatus.FAILED
                )
            else:
                batch.status = BatchStatus.COMPLETED

    def list_recent_batches(self, limit: int = 50) -> List[BatchProgressResponse]:
        with self._lock:
            recent = list(self._store.values())[-limit:]
            recent.reverse()
            return [b.to_progress_response() for b in recent]

    def clear(self):
        """Helper to clear all stored batches (useful for test isolation and administrative reset)."""
        with self._lock:
            self._store.clear()

    def get_stats(self) -> dict:
        """Helper returning storage metrics, batch counts, and capacity utilization."""
        with self._lock:
            return {
                "total_stored_batches": len(self._store),
                "max_capacity": self.max_capacity,
                "ttl_seconds": self.ttl_seconds,
                "active_processing_batches": sum(
                    1 for b in self._store.values() if b.status == BatchStatus.PROCESSING
                ),
            }


# Singleton instance for assignment in-memory operation
_default_repo: Optional[InMemoryBatchRepository] = None


def get_batch_repository() -> InMemoryBatchRepository:
    """Dependency injection provider for the in-memory batch repository."""
    global _default_repo
    if _default_repo is None:
        from app.config import get_settings
        settings = get_settings()
        _default_repo = InMemoryBatchRepository(
            max_capacity=settings.MAX_BATCH_STORE_SIZE,
            ttl_seconds=settings.BATCH_TTL_SECONDS,
        )
    return _default_repo
