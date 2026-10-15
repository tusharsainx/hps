"""Unit tests for InMemoryBatchRepository implementation."""

import pytest
from app.services.batch_repository import InMemoryBatchRepository
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

