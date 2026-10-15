"""Core bulk processing orchestrator for hospital batches."""

import asyncio
import logging
from typing import List, Optional
import uuid

from app.config import Settings, get_settings
from app.models.batch import (
    BulkProcessResponse,
    BatchProgressResponse,
    HospitalBatchItem,
)
from app.models.hospital import HospitalCreate, HospitalRecord
from app.services.hospital_client import HospitalClient, UpstreamApiException
from app.services.batch_repository import (
    BaseBatchRepository,
    get_batch_repository,
)

logger = logging.getLogger(__name__)


class BulkProcessor:
    """Orchestrates asynchronous bulk hospital ingestion, activation, and resumption."""

    def __init__(
        self,
        client: Optional[HospitalClient] = None,
        repository: Optional[BaseBatchRepository] = None,
        settings: Optional[Settings] = None,
    ):
        self.settings = settings or get_settings()
        self.client = client or HospitalClient(settings=self.settings)
        self.repository = repository or get_batch_repository()
        self.concurrency_limit = self.settings.CONCURRENCY_LIMIT

    async def process_batch(
        self,
        records: List[HospitalRecord],
        batch_id: Optional[str] = None,
    ) -> BulkProcessResponse:
        """Process a list of hospital records as a single batch."""
        if not batch_id:
            batch_id = str(uuid.uuid4())

        # Initialize repository state
        batch = self.repository.create_batch(batch_id=batch_id, records=records)

        semaphore = asyncio.Semaphore(self.concurrency_limit)

        async def _worker(rec: HospitalRecord):
            async with semaphore:
                try:
                    payload = HospitalCreate(
                        name=rec.name,
                        address=rec.address,
                        phone=rec.phone,
                        creation_batch_id=batch_id,
                    )
                    resp = await self.client.create_hospital(payload)
                    self.repository.update_row_success(
                        batch_id=batch_id,
                        row=rec.row,
                        hospital_id=resp.id,
                    )
                except UpstreamApiException as exc:
                    logger.error(
                        "Upstream API error creating hospital row %d for batch %s: %s",
                        rec.row, batch_id, exc.message,
                    )
                    self.repository.update_row_failure(
                        batch_id=batch_id,
                        row=rec.row,
                        error_message=exc.message,
                    )
                except Exception as exc:
                    logger.exception(
                        "Unexpected error creating hospital row %d for batch %s: %s",
                        rec.row, batch_id, exc,
                    )
                    self.repository.update_row_failure(
                        batch_id=batch_id,
                        row=rec.row,
                        error_message=f"Internal failure: {str(exc)}",
                    )

        # Run creation tasks with bounded concurrency
        await asyncio.gather(*[_worker(rec) for rec in records])

        # Check if all records succeeded
        batch_after = self.repository.get_batch(batch_id)
        if not batch_after:
            raise RuntimeError(f"Batch {batch_id} not found in state store.")

        all_succeeded = (
            batch_after.processed_hospitals == batch_after.total_hospitals
            and batch_after.failed_hospitals == 0
        )

        activated = False
        if all_succeeded:
            try:
                logger.info("All %d hospitals created for batch %s. Activating...", batch_after.total_hospitals, batch_id)
                await self.client.activate_batch(batch_id)
                activated = True
                logger.info("Batch %s successfully activated.", batch_id)
            except Exception as exc:
                logger.error("Failed to activate batch %s: %s", batch_id, exc)
                # Keep activated as False

        self.repository.complete_batch(batch_id=batch_id, activated=activated)
        final_state = self.repository.get_batch(batch_id)
        if final_state:
            return final_state.to_bulk_response()

        raise RuntimeError(f"Failed to finalize batch {batch_id}.")

    async def resume_batch(self, batch_id: str) -> BulkProcessResponse:
        """Resume a failed or partially completed batch.
        
        Fetches existing hospitals upstream, skips already created ones,
        retries failed records, and activates the batch when all are created.
        """
        batch = self.repository.get_batch(batch_id)
        if not batch:
            raise KeyError(f"Batch {batch_id} not found in repository.")

        if batch.batch_activated:
            logger.info("Batch %s is already activated. Returning current state.", batch_id)
            return batch.to_bulk_response()

        # Check existing hospitals created upstream
        try:
            upstream_hospitals = await self.client.get_hospitals_by_batch(batch_id)
            created_names = {h.name.strip().lower(): h.id for h in upstream_hospitals}
        except Exception as exc:
            logger.warning("Could not query upstream batch %s: %s. Using local state.", batch_id, exc)
            created_names = {}

        # Identify records that still need creation
        records_to_retry: List[HospitalRecord] = []
        for row, rec in batch.source_records.items():
            item = batch.hospitals.get(row)
            name_key = rec.name.strip().lower()

            # If already created upstream or marked as created locally with ID
            if name_key in created_names:
                self.repository.update_row_success(batch_id, row, created_names[name_key])
            elif item and item.hospital_id is not None and item.status in ("created", "created_and_activated"):
                continue
            else:
                records_to_retry.append(rec)

        if records_to_retry:
            logger.info("Resuming batch %s: Retrying %d records.", batch_id, len(records_to_retry))
            semaphore = asyncio.Semaphore(self.concurrency_limit)

            async def _retry_worker(rec: HospitalRecord):
                async with semaphore:
                    try:
                        payload = HospitalCreate(
                            name=rec.name,
                            address=rec.address,
                            phone=rec.phone,
                            creation_batch_id=batch_id,
                        )
                        resp = await self.client.create_hospital(payload)
                        self.repository.update_row_success(
                            batch_id=batch_id,
                            row=rec.row,
                            hospital_id=resp.id,
                        )
                    except Exception as exc:
                        logger.error("Retry failed for row %d in batch %s: %s", rec.row, batch_id, exc)
                        self.repository.update_row_failure(
                            batch_id=batch_id,
                            row=rec.row,
                            error_message=str(exc),
                        )

            await asyncio.gather(*[_retry_worker(r) for r in records_to_retry])

        # Check if all records are now created
        refreshed = self.repository.get_batch(batch_id)
        if not refreshed:
            raise RuntimeError(f"Batch {batch_id} lost during resumption.")

        all_succeeded = (
            refreshed.processed_hospitals == refreshed.total_hospitals
            and refreshed.failed_hospitals == 0
        )

        activated = False
        if all_succeeded:
            try:
                await self.client.activate_batch(batch_id)
                activated = True
            except Exception as exc:
                logger.error("Failed to activate batch %s after resumption: %s", batch_id, exc)

        self.repository.complete_batch(batch_id=batch_id, activated=activated)
        final_state = self.repository.get_batch(batch_id)
        if final_state:
            return final_state.to_bulk_response()

        raise RuntimeError(f"Failed to finalize resumed batch {batch_id}.")

    async def delete_batch(self, batch_id: str) -> dict:
        """Rollback/delete an entire batch from the upstream service."""
        return await self.client.delete_batch(batch_id)
