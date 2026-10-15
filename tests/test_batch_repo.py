"""Unit tests for repository implementations (In-Memory and Persistent SQLite)."""

import pytest
import os
import tempfile
from app.services.batch_repository import (
    InMemoryBatchRepository,
    PersistentSqliteBatchRepository,
)
from app.models.hospital import HospitalRecord
from app.models.batch import BatchStatus


@pytest.fixture
def sample_records():
    return [
        HospitalRecord(row=1, name="Hospital A", address="100 A St", phone="555-01"),
        HospitalRecord(row=2, name="Hospital B", address="200 B St", phone="555-02"),
    ]


def test_in_memory_repository_lifecycle(sample_records):
    repo = InMemoryBatchRepository()
    batch_id = "test-mem-1"

    # Create
    batch = repo.create_batch(batch_id, sample_records)
    assert batch.total_hospitals == 2
    assert batch.status == BatchStatus.PROCESSING

    # Update row 1 success
    repo.update_row_success(batch_id, 1, 101)
    b = repo.get_batch(batch_id)
    assert b.processed_hospitals == 1
    assert b.failed_hospitals == 0

    # Update row 2 failure
    repo.update_row_failure(batch_id, 2, "Timeout")
    b = repo.get_batch(batch_id)
    assert b.processed_hospitals == 1
    assert b.failed_hospitals == 1

    # Complete batch without activation
    repo.complete_batch(batch_id, activated=False)
    b = repo.get_batch(batch_id)
    assert b.status == BatchStatus.PARTIALLY_FAILED
    assert b.batch_activated is False

    # Verify helpers: get_stats and clear
    stats = repo.get_stats()
    assert stats["total_stored_batches"] == 1
    assert stats["max_capacity"] == 10000

    repo.clear()
    assert repo.get_stats()["total_stored_batches"] == 0
    assert repo.get_batch(batch_id) is None


def test_sqlite_persistent_repository_lifecycle(sample_records):
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        repo = PersistentSqliteBatchRepository(db_path=db_path)
        batch_id = "test-sqlite-1"

        # Create
        batch = repo.create_batch(batch_id, sample_records)
        assert batch.total_hospitals == 2

        # Update row 1 success
        repo.update_row_success(batch_id, 1, 201)
        b = repo.get_batch(batch_id)
        assert b.processed_hospitals == 1
        assert b.hospitals[1].hospital_id == 201
        assert b.hospitals[1].status == "created"

        # Update row 2 success
        repo.update_row_success(batch_id, 2, 202)
        b = repo.get_batch(batch_id)
        assert b.processed_hospitals == 2

        # Complete with activation
        repo.complete_batch(batch_id, activated=True)
        b = repo.get_batch(batch_id)
        assert b.status == BatchStatus.ACTIVATED
        assert b.batch_activated is True
        assert b.hospitals[1].status == "created_and_activated"
        assert b.hospitals[2].status == "created_and_activated"

        # Verify listing
        recent = repo.list_recent_batches(10)
        assert len(recent) == 1
        assert recent[0].batch_id == batch_id
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)
