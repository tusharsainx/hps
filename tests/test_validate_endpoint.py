"""Integration tests for POST /hospitals/bulk/validate endpoint."""

import pytest


@pytest.mark.asyncio
async def test_validate_csv_endpoint_valid(async_client, valid_5_csv_bytes):
    files = {"file": ("valid.csv", valid_5_csv_bytes, "text/csv")}
    response = await async_client.post("/hospitals/bulk/validate", files=files)

    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is True
    assert data["total_rows"] == 5
    assert len(data["errors"]) == 0


@pytest.mark.asyncio
async def test_validate_csv_endpoint_exceeds_limit(async_client, exceed_limit_csv_bytes):
    files = {"file": ("exceed.csv", exceed_limit_csv_bytes, "text/csv")}
    response = await async_client.post("/hospitals/bulk/validate", files=files)

    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is False
    assert data["total_rows"] == 25
    assert any("exceeds the maximum allowed limit of 20 hospitals" in err["message"] for err in data["errors"])


@pytest.mark.asyncio
async def test_validate_csv_endpoint_missing_columns(async_client):
    csv_bytes = b"facility,address\nHospital 1,123 Main St\n"
    files = {"file": ("missing_col.csv", csv_bytes, "text/csv")}
    response = await async_client.post("/hospitals/bulk/validate", files=files)

    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is False
    assert any("Missing required CSV column" in err["message"] for err in data["errors"])
