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
        """Export state for progress polling and WebSocket updates."""
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
    """Thread-safe in-memory batch repository with bounded LRU eviction."""

    def __init__(self, max_capacity: int = 10000):
        self._lock = threading.Lock()
        self._store: OrderedDict[str, BatchRecordInternal] = OrderedDict()
        self.max_capacity = max_capacity

    def create_batch(self, batch_id: str, records: List[HospitalRecord]) -> BatchRecordInternal:
        with self._lock:
            # Enforce LRU eviction if capacity is reached
            if len(self._store) >= self.max_capacity:
                self._store.popitem(last=False)

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
                "active_processing_batches": sum(
                    1 for b in self._store.values() if b.status == BatchStatus.PROCESSING
                ),
            }


class PersistentSqliteBatchRepository(BaseBatchRepository):
    """Enterprise-ready SQLite persistent repository for durable multi-worker batch storage."""

    def __init__(self, db_path: str = "batches.db"):
        import sqlite3
        self.db_path = db_path
        self._lock = threading.Lock()
        self._init_db()

    def _get_connection(self):
        import sqlite3
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        return conn

    def _init_db(self):
        with self._lock:
            with self._get_connection() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS batches (
                        batch_id TEXT PRIMARY KEY,
                        total_hospitals INTEGER,
                        processed_hospitals INTEGER DEFAULT 0,
                        failed_hospitals INTEGER DEFAULT 0,
                        status TEXT,
                        batch_activated INTEGER DEFAULT 0,
                        start_time REAL,
                        end_time REAL,
                        processing_time_seconds REAL DEFAULT 0.0
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS batch_items (
                        batch_id TEXT,
                        row INTEGER,
                        hospital_id INTEGER,
                        name TEXT,
                        address TEXT,
                        phone TEXT,
                        status TEXT,
                        error TEXT,
                        PRIMARY KEY (batch_id, row)
                    )
                    """
                )
                conn.commit()

    def create_batch(self, batch_id: str, records: List[HospitalRecord]) -> BatchRecordInternal:
        batch = BatchRecordInternal(batch_id=batch_id, total_hospitals=len(records))
        batch.status = BatchStatus.PROCESSING

        with self._lock:
            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO batches (batch_id, total_hospitals, processed_hospitals, failed_hospitals, status, batch_activated, start_time, processing_time_seconds)
                    VALUES (?, ?, 0, 0, ?, 0, ?, 0.0)
                    """,
                    (batch_id, len(records), BatchStatus.PROCESSING.value, batch.start_time),
                )
                for rec in records:
                    batch.source_records[rec.row] = rec
                    batch.hospitals[rec.row] = HospitalBatchItem(
                        row=rec.row,
                        hospital_id=None,
                        name=rec.name,
                        status="pending",
                        error=None,
                    )
                    conn.execute(
                        """
                        INSERT INTO batch_items (batch_id, row, hospital_id, name, address, phone, status, error)
                        VALUES (?, ?, NULL, ?, ?, ?, 'pending', NULL)
                        """,
                        (batch_id, rec.row, rec.name, rec.address, rec.phone),
                    )
                conn.commit()
        return batch

    def get_batch(self, batch_id: str) -> Optional[BatchRecordInternal]:
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.execute("SELECT * FROM batches WHERE batch_id = ?", (batch_id,))
                b_row = cursor.fetchone()
                if not b_row:
                    return None

                batch = BatchRecordInternal(batch_id=batch_id, total_hospitals=b_row["total_hospitals"])
                batch.processed_hospitals = b_row["processed_hospitals"]
                batch.failed_hospitals = b_row["failed_hospitals"]
                batch.status = BatchStatus(b_row["status"])
                batch.batch_activated = bool(b_row["batch_activated"])
                batch.start_time = b_row["start_time"]
                batch.end_time = b_row["end_time"]
                batch.processing_time_seconds = b_row["processing_time_seconds"]

                item_cursor = conn.execute("SELECT * FROM batch_items WHERE batch_id = ? ORDER BY row ASC", (batch_id,))
                for i_row in item_cursor.fetchall():
                    row_idx = i_row["row"]
                    batch.source_records[row_idx] = HospitalRecord(
                        row=row_idx,
                        name=i_row["name"],
                        address=i_row["address"],
                        phone=i_row["phone"],
                    )
                    batch.hospitals[row_idx] = HospitalBatchItem(
                        row=row_idx,
                        hospital_id=i_row["hospital_id"],
                        name=i_row["name"],
                        status=i_row["status"],
                        error=i_row["error"],
                    )
                return batch

    def update_row_success(self, batch_id: str, row: int, hospital_id: int):
        with self._lock:
            with self._get_connection() as conn:
                conn.execute(
                    """
                    UPDATE batch_items
                    SET hospital_id = ?, status = 'created', error = NULL
                    WHERE batch_id = ? AND row = ?
                    """,
                    (hospital_id, batch_id, row),
                )
                self._recalculate_batch_counts(conn, batch_id)
                conn.commit()

    def update_row_failure(self, batch_id: str, row: int, error_message: str):
        with self._lock:
            with self._get_connection() as conn:
                conn.execute(
                    """
                    UPDATE batch_items
                    SET status = 'failed', error = ?
                    WHERE batch_id = ? AND row = ?
                    """,
                    (error_message, batch_id, row),
                )
                self._recalculate_batch_counts(conn, batch_id)
                conn.commit()

    def _recalculate_batch_counts(self, conn, batch_id: str):
        cursor = conn.execute(
            """
            SELECT
                SUM(CASE WHEN status IN ('created', 'created_and_activated') THEN 1 ELSE 0 END) as processed,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed
            FROM batch_items WHERE batch_id = ?
            """,
            (batch_id,),
        )
        counts = cursor.fetchone()
        conn.execute(
            "UPDATE batches SET processed_hospitals = ?, failed_hospitals = ? WHERE batch_id = ?",
            (counts["processed"] or 0, counts["failed"] or 0, batch_id),
        )

    def complete_batch(self, batch_id: str, activated: bool):
        with self._lock:
            with self._get_connection() as conn:
                end_time = time.time()
                cur = conn.execute("SELECT start_time, failed_hospitals, processed_hospitals FROM batches WHERE batch_id = ?", (batch_id,))
                row = cur.fetchone()
                if not row:
                    return

                duration = round(end_time - row["start_time"], 2)
                if activated:
                    status_val = BatchStatus.ACTIVATED.value
                    conn.execute(
                        "UPDATE batch_items SET status = 'created_and_activated' WHERE batch_id = ? AND status = 'created'",
                        (batch_id,),
                    )
                elif (row["failed_hospitals"] or 0) > 0:
                    status_val = (
                        BatchStatus.PARTIALLY_FAILED.value
                        if (row["processed_hospitals"] or 0) > 0
                        else BatchStatus.FAILED.value
                    )
                else:
                    status_val = BatchStatus.COMPLETED.value

                conn.execute(
                    """
                    UPDATE batches
                    SET status = ?, batch_activated = ?, end_time = ?, processing_time_seconds = ?
                    WHERE batch_id = ?
                    """,
                    (status_val, 1 if activated else 0, end_time, duration, batch_id),
                )
                conn.commit()

    def list_recent_batches(self, limit: int = 50) -> List[BatchProgressResponse]:
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    "SELECT batch_id FROM batches ORDER BY start_time DESC LIMIT ?", (limit,)
                )
                batch_ids = [r["batch_id"] for r in cursor.fetchall()]

        results = []
        for b_id in batch_ids:
            b = self.get_batch(b_id)
            if b:
                results.append(b.to_progress_response())
        return results


# Default repository singleton instance
_default_repo: Optional[BaseBatchRepository] = None


def get_batch_repository() -> BaseBatchRepository:
    """Dependency injection provider for the batch repository.
    
    Dynamically instantiates the storage backend according to Settings:
    - Standard Scale: 'memory' (InMemoryBatchRepository)
    - Enterprise Scale: 'database' (PersistentSqliteBatchRepository / Postgres)
    """
    global _default_repo
    if _default_repo is None:
        from app.config import get_settings
        settings = get_settings()
        if settings.STORAGE_BACKEND == "database":
            db_path = settings.DATABASE_URL.replace("sqlite:///", "")
            _default_repo = PersistentSqliteBatchRepository(db_path=db_path)
        else:
            _default_repo = InMemoryBatchRepository(max_capacity=settings.MAX_BATCH_STORE_SIZE)
    return _default_repo
