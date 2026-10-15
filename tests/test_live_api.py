"""End-to-End Live Integration Test against the deployed Render Hospital Directory API."""

import pytest
import uuid
from app.services.hospital_client import HospitalClient
from app.models.hospital import HospitalCreate
from app.config import get_settings


@pytest.mark.live
@pytest.mark.asyncio
async def test_live_render_api_lifecycle():
    """Verify live lifecycle against https://hospital-directory.onrender.com."""
    settings = get_settings()
    client = HospitalClient(settings=settings)

    # 1. Check health
    health_ok = await client.check_health()
    if not health_ok:
        pytest.skip("Live Hospital Directory API is currently unreachable.")

    test_batch_id = str(uuid.uuid4())

    try:
        # 2. Create hospital 1
        h1 = await client.create_hospital(
            HospitalCreate(
                name="Live Test Hospital Alpha",
                address="100 E2E Parkway",
                phone="555-0101",
                creation_batch_id=test_batch_id,
            )
        )
        assert h1.id is not None
        assert h1.active is False

        # 3. Create hospital 2
        h2 = await client.create_hospital(
            HospitalCreate(
                name="Live Test Hospital Beta",
                address="200 E2E Parkway",
                phone="555-0102",
                creation_batch_id=test_batch_id,
            )
        )
        assert h2.id is not None
        assert h2.active is False

        # 4. Verify batch listing
        batch_items = await client.get_hospitals_by_batch(test_batch_id)
        assert len(batch_items) >= 2

        # 5. Activate batch
        activate_res = await client.activate_batch(test_batch_id)
        assert activate_res.get("activated_count", 0) >= 2

    finally:
        # 6. Cleanup: Delete batch from live upstream
        await client.delete_batch(test_batch_id)
        await client.close()
