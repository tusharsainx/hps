"""Integration tests for POST /hospitals/bulk endpoint."""

import pytest
import respx
import httpx
from app.config import get_settings


@pytest.mark.asyncio
@respx.mock
async def test_bulk_create_hospitals_success(async_client, valid_5_csv_bytes):
    settings = get_settings()
    base_url = settings.HOSPITAL_API_BASE_URL.rstrip("/")

    # Mock individual creation
    def create_side_effect(request):
        import json
        body = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "id": 100 + len(respx.calls),
                "name": body["name"],
                "address": body["address"],
                "phone": body.get("phone"),
                "creation_batch_id": body.get("creation_batch_id"),
                "active": False,
                "created_at": "2026-10-15T08:00:00Z",
            },
        )

    respx.post(f"{base_url}/hospitals/").mock(side_effect=create_side_effect)
    respx.patch(url__regex=rf"{base_url}/hospitals/batch/.+/activate").respond(
        status_code=200,
        json={"activated_count": 5, "message": "Activated 5 hospitals"},
    )

    files = {"file": ("test_hospitals.csv", valid_5_csv_bytes, "text/csv")}
    
    # 1. Test background mode (default): returns 202 Accepted immediately
    response = await async_client.post("/hospitals/bulk", files=files)
    assert response.status_code == 202
    data = response.json()

    assert "batch_id" in data
    batch_id = data["batch_id"]
    assert data["total_hospitals"] == 5

    # Poll status endpoint for the background-processed batch
    status_resp = await async_client.get(f"/hospitals/bulk/{batch_id}")
    assert status_resp.status_code == 200
    status_data = status_resp.json()
    assert status_data["batch_id"] == batch_id
    assert status_data["total_hospitals"] == 5
    assert status_data["processed_hospitals"] == 5
    assert status_data["failed_hospitals"] == 0
    assert status_data["batch_activated"] is True
    assert isinstance(status_data["processing_time_seconds"], float)
    assert len(status_data["hospitals"]) == 5

    first = status_data["hospitals"][0]
    assert first["row"] == 1
    assert first["name"] == "Hospital A"
    assert first["status"] == "created_and_activated"
    assert first["hospital_id"] is not None

    # 2. Test synchronous mode (?sync=true): blocks and returns 200 OK directly
    files_sync = {"file": ("test_sync.csv", valid_5_csv_bytes, "text/csv")}
    sync_resp = await async_client.post("/hospitals/bulk?sync=true", files=files_sync)
    assert sync_resp.status_code == 200
    sync_data = sync_resp.json()
    assert sync_data["batch_activated"] is True
    assert sync_data["processed_hospitals"] == 5


@pytest.mark.asyncio
async def test_bulk_create_rejects_non_csv(async_client):
    files = {"file": ("data.txt", b"some,text,data", "text/plain")}
    response = await async_client.post("/hospitals/bulk", files=files)
    assert response.status_code == 400
    assert "Invalid file type" in response.json()["detail"]["message"]


@pytest.mark.asyncio
async def test_bulk_create_rejects_exceeding_20_rows(async_client, exceed_limit_csv_bytes):
    files = {"file": ("exceed_25.csv", exceed_limit_csv_bytes, "text/csv")}
    response = await async_client.post("/hospitals/bulk", files=files)

    # Must NOT be 413 Payload Too Large as explicitly requested
    assert response.status_code != 413
    assert response.status_code == 422
    data = response.json()
    assert "exceeds the maximum allowed limit of 20 hospitals" in str(data)


@pytest.mark.asyncio
@respx.mock
async def test_health_and_root_head_methods_supported(async_client):
    """Verify that HEAD and GET requests are supported for uptime monitoring."""
    settings = get_settings()
    base_url = settings.HOSPITAL_API_BASE_URL.rstrip("/")
    respx.get(f"{base_url}/health").respond(200, json={"status": "healthy"})

    # Test HEAD on /health (UptimeRobot default method)
    head_resp = await async_client.head("/health")
    assert head_resp.status_code == 200

    # Test GET on /health
    get_resp = await async_client.get("/health")
    assert get_resp.status_code == 200
    assert get_resp.json()["status"] == "healthy"

    # Test HEAD on root /
    root_head = await async_client.head("/", follow_redirects=False)
    assert root_head.status_code == 307
