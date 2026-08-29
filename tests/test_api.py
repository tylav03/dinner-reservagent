"""HTTP surface: the endpoints the demo web app relies on. Needs Postgres."""

from __future__ import annotations

from datetime import datetime, timedelta


def _friday_7pm_iso() -> str:
    d = datetime.now().date()
    while d.weekday() != 4:
        d += timedelta(days=1)
    d += timedelta(days=7)
    return datetime(d.year, d.month, d.day, 19, 0).isoformat()


def test_healthz(client):
    assert client.get("/healthz").json() == {"status": "ok"}


def test_config_endpoint(client):
    cfg = client.get("/api/config").json()
    assert cfg["name"] == "The Copper Fork"
    assert len(cfg["tables"]) == 14
    assert cfg["turn_time_minutes"] == 90


def test_create_then_list_and_fetch(client):
    body = {
        "guest_name": "Katherine Johnson",
        "phone": "+15550123",
        "party_size": 2,
        "when": _friday_7pm_iso(),
    }
    created = client.post("/api/reservations", json=body)
    assert created.status_code == 201, created.text
    code = created.json()["confirmation_code"]

    listed = client.get("/api/reservations").json()
    assert any(r["confirmation_code"] == code for r in listed)

    one = client.get(f"/api/reservations/{code}")
    assert one.status_code == 200
    assert one.json()["guest_name"] == "Katherine Johnson"


def test_availability_endpoint_reports_reason(client):
    # lunchtime -> closed
    when = _friday_7pm_iso().replace("T19:00:00", "T12:30:00")
    res = client.get("/api/availability", params={"when": when, "party_size": 2}).json()
    assert res["available"] is False
    assert res["reason"] == "closed"


def test_double_book_returns_409_with_alternatives(client):
    when = _friday_7pm_iso()
    # book all 14 tables
    for i in range(14):
        r = client.post("/api/reservations", json={
            "guest_name": f"G{i}", "phone": f"+1555{i:04d}", "party_size": 2, "when": when,
        })
        assert r.status_code == 201, r.text
    clash = client.post("/api/reservations", json={
        "guest_name": "late", "phone": "+15559999", "party_size": 2, "when": when,
    })
    assert clash.status_code == 409
    detail = clash.json()["detail"]
    assert detail["reason"] == "full"
    assert len(detail["alternatives"]) >= 1


def test_cancel_endpoint(client):
    created = client.post("/api/reservations", json={
        "guest_name": "Mary Jackson", "phone": "+15550199", "party_size": 4,
        "when": _friday_7pm_iso(),
    }).json()
    code = created["confirmation_code"]
    deleted = client.delete(f"/api/reservations/{code}")
    assert deleted.status_code == 200
    assert deleted.json()["status"] == "cancelled"


def test_free_text_when_is_accepted(client):
    res = client.post("/api/reservations", json={
        "guest_name": "Free Text", "phone": "+15550142", "party_size": 2,
        "when": "next Friday at 7pm",
    })
    # The free-text date must parse (not 422); booking itself may 201 or 409.
    assert res.status_code in (201, 409), res.text
