"""Integration tests for Resume Capability (POST /hospitals/bulk/{batch_id}/resume)."""

import pytest
import respx
import httpx
from app.config import get_settings


@pytest.mark.asyncio
@respx.mock
async def test_resume_failed_bulk_operation(async_client):
    settings = get_settings()
    base_url = settings.HOSPITAL_API_BASE_URL.rstrip("/")

    # Upload CSV with 3 hospitals
    csv_bytes = (
        b"name,address,phone\n"
        b"Alpha Clinic,100 Alpha St,555-1111\n"
        b"Beta Hospital,200 Beta St,555-2222\n"
        b"Gamma Care,300 Gamma St,555-3333\n"
    )

    call_index = 0

    def mock_create(request):
        nonlocal call_index
        import json
        call_index += 1
        body = json.loads(request.content)
        # Force Gamma Care to fail initially
        if body["name"] == "Gamma Care" and call_index <= 3:
            return httpx.Response(500, text="Temporary DB lock")
        return httpx.Response(
            200,
            json={
                "id": 200 + call_index,
                "name": body["name"],
                "address": body["address"],
                "phone": body.get("phone"),
                "creation_batch_id": body.get("creation_batch_id"),
                "active": False,
            },
        )

    respx.post(f"{base_url}/hospitals/").mock(side_effect=mock_create)
    respx.patch(url__regex=rf"{base_url}/hospitals/batch/.+/activate").respond(
        status_code=200,
        json={"activated_count": 3, "message": "Activated 3 hospitals"},
    )
    respx.get(url__regex=rf"{base_url}/hospitals/batch/.+").respond(
        status_code=200,
        json=[
            {"id": 201, "name": "Alpha Clinic", "address": "100 Alpha St", "phone": "555-1111", "active": False},
            {"id": 202, "name": "Beta Hospital", "address": "200 Beta St", "phone": "555-2222", "active": False},
        ],
    )

    # 1. Initial Upload -> Gamma Care fails, so batch should NOT be activated
    files = {"file": ("test.csv", csv_bytes, "text/csv")}
    resp1 = await async_client.post("/hospitals/bulk", files=files)
    data1 = resp1.json()

    assert resp1.status_code == 200
    batch_id = data1["batch_id"]
    assert data1["total_hospitals"] == 3
    assert data1["failed_hospitals"] == 1
    assert data1["batch_activated"] is False

    # 2. Call Resume on this batch ID
    resp2 = await async_client.post(f"/hospitals/bulk/{batch_id}/resume")
    assert resp2.status_code == 200
    data2 = resp2.json()

    # Now all 3 should be processed and batch activated
    assert data2["batch_id"] == batch_id
    assert data2["total_hospitals"] == 3
    assert data2["processed_hospitals"] == 3
    assert data2["failed_hospitals"] == 0
    assert data2["batch_activated"] is True
