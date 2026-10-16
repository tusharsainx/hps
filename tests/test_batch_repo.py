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


def test_in_memory_repository_lru_eviction(sample_records):
    """Test that LRU eviction removes the oldest batch when max_capacity is reached."""
    repo = InMemoryBatchRepository(max_capacity=2)
    repo.create_batch("batch-1", sample_records)
    repo.create_batch("batch-2", sample_records)
    assert repo.get_stats()["total_stored_batches"] == 2
    assert repo.get_batch("batch-1") is not None
    assert repo.get_batch("batch-2") is not None

    # Inserting 3rd batch evicts the oldest (batch-1)
    repo.create_batch("batch-3", sample_records)
    assert repo.get_stats()["total_stored_batches"] == 2
    assert repo.get_batch("batch-1") is None
    assert repo.get_batch("batch-2") is not None
    assert repo.get_batch("batch-3") is not None


def test_in_memory_repository_ttl_eviction(sample_records):
    """Test that completed batches older than TTL are automatically evicted."""
    repo = InMemoryBatchRepository(max_capacity=10, ttl_seconds=10)
    batch = repo.create_batch("batch-old", sample_records)
    repo.complete_batch("batch-old", activated=True)

    # Backdate start_time to simulate 15 seconds ago (> 10s TTL)
    batch.start_time = batch.start_time - 15

    # Creating a new batch triggers cleanup
    repo.create_batch("batch-new", sample_records)
    assert repo.get_batch("batch-old") is None
    assert repo.get_batch("batch-new") is not None

