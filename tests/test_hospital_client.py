"""Unit tests for the resilient upstream HospitalClient."""

import pytest
import respx
import httpx
from app.services.hospital_client import HospitalClient, UpstreamApiException
from app.models.hospital import HospitalCreate


@pytest.mark.asyncio
@respx.mock
async def test_create_hospital_success(test_settings):
    base_url = test_settings.HOSPITAL_API_BASE_URL
    route = respx.post(f"{base_url}/hospitals/").respond(
        status_code=200,
        json={
            "id": 101,
            "name": "General Hospital",
            "address": "123 Elm St",
            "phone": "555-0100",
            "creation_batch_id": "test-uuid-1",
            "active": False,
            "created_at": "2026-10-15T08:00:00Z",
        },
    )

    client = HospitalClient(settings=test_settings)
    payload = HospitalCreate(
        name="General Hospital",
        address="123 Elm St",
        phone="555-0100",
        creation_batch_id="test-uuid-1",
    )
    result = await client.create_hospital(payload)

    assert route.called
    assert result.id == 101
    assert result.name == "General Hospital"
    assert result.active is False
    await client.close()


@pytest.mark.asyncio
@respx.mock
async def test_activate_batch_success(test_settings):
    base_url = test_settings.HOSPITAL_API_BASE_URL
    batch_id = "test-uuid-activate"
    route = respx.patch(f"{base_url}/hospitals/batch/{batch_id}/activate").respond(
        status_code=200,
        json={"activated_count": 5, "message": f"Activated 5 hospital(s) with batch ID {batch_id}"},
    )

    client = HospitalClient(settings=test_settings)
    result = await client.activate_batch(batch_id)

    assert route.called
    assert result["activated_count"] == 5
    await client.close()


@pytest.mark.asyncio
@respx.mock
async def test_retry_on_transient_error(test_settings):
    base_url = test_settings.HOSPITAL_API_BASE_URL
    # Fail first call with 503, succeed on second attempt
    route = respx.post(f"{base_url}/hospitals/").mock(
        side_effect=[
            httpx.Response(503, text="Service Unavailable"),
            httpx.Response(
                200,
                json={
                    "id": 102,
                    "name": "Recovered Hospital",
                    "address": "456 Oak St",
                    "creation_batch_id": "uuid-retry",
                    "active": False,
                },
            ),
        ]
    )

    client = HospitalClient(settings=test_settings)
    payload = HospitalCreate(
        name="Recovered Hospital",
        address="456 Oak St",
        creation_batch_id="uuid-retry",
    )
    result = await client.create_hospital(payload)

    assert route.call_count == 2
    assert result.id == 102
    await client.close()


@pytest.mark.asyncio
@respx.mock
async def test_non_retryable_422_error(test_settings):
    base_url = test_settings.HOSPITAL_API_BASE_URL
    route = respx.post(f"{base_url}/hospitals/").respond(
        status_code=422,
        json={"detail": [{"loc": ["body", "name"], "msg": "String should have at least 1 character", "type": "string_too_short"}]},
    )

    client = HospitalClient(settings=test_settings)
    payload = HospitalCreate(name="X", address="Y")

    with pytest.raises(UpstreamApiException) as exc_info:
        await client.create_hospital(payload)

    assert exc_info.value.status_code == 422
    assert route.call_count == 1  # No wasteful retry on 422
    await client.close()
