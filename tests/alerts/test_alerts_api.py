import pytest


@pytest.mark.asyncio
async def test_alerts_crud_and_ownership(async_client) -> None:
    reg = await async_client.post("/api/v1/alerts/subscribers/register")
    assert reg.status_code == 200
    body = reg.json()
    token = body["bearer_token"]
    assert body["subscriber_id"]
    assert isinstance(body["bearer_token"], str) and len(body["bearer_token"]) >= 16

    headers = {"Authorization": f"Bearer {token}"}
    other = await async_client.post("/api/v1/alerts/subscribers/register")
    other_token = other.json()["bearer_token"]

    create = await async_client.post(
        "/api/v1/alerts/searches",
        headers=headers,
        json={"q": "engineer", "country_code": "pk", "alerts_enabled": True},
    )
    assert create.status_code == 201
    search_id = create.json()["id"]
    assert create.json()["country_code"] == "PK"

    list_resp = await async_client.get("/api/v1/alerts/searches", headers=headers)
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1

    forbidden = await async_client.get(
        "/api/v1/alerts/searches",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert forbidden.status_code == 200
    assert forbidden.json() == []

    patch = await async_client.patch(
        f"/api/v1/alerts/searches/{search_id}",
        headers=headers,
        json={"q": "software"},
    )
    assert patch.status_code == 200
    assert patch.json()["q"] == "software"

    await async_client.post(f"/api/v1/alerts/searches/{search_id}/disable", headers=headers)
    delete = await async_client.delete(f"/api/v1/alerts/searches/{search_id}", headers=headers)
    assert delete.status_code == 204


@pytest.mark.asyncio
async def test_digest_run_returns_404_when_disabled(async_client) -> None:
    reg = await async_client.post("/api/v1/alerts/subscribers/register")
    token = reg.json()["bearer_token"]
    resp = await async_client.post(
        "/api/v1/alerts/digest/run",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404