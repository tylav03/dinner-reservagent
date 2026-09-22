"""HTTP surface: the endpoints the demo web app relies on. Needs Postgres."""

from __future__ import annotations

from datetime import datetime, timedelta


def _next_weekday_date(weekday: int, plus_weeks: int = 1) -> str:
    d = datetime.now().date()
    while d.weekday() != weekday:
        d += timedelta(days=1)
    d += timedelta(days=7 * plus_weeks)
    return d.isoformat()


def _friday_7pm_iso() -> str:
    return f"{_next_weekday_date(4)}T19:00:00"


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


def test_patch_endpoint_updates_status_and_notes(client):
    created = client.post("/api/reservations", json={
        "guest_name": "Dorothy Vaughan", "phone": "+15550188", "party_size": 3,
        "when": _friday_7pm_iso(),
    }).json()
    code = created["confirmation_code"]

    patched = client.patch(f"/api/reservations/{code}", json={
        "status": "seated", "notes": "arrived early",
    })
    assert patched.status_code == 200, patched.text
    body = patched.json()
    assert body["status"] == "seated"
    assert body["notes"] == "arrived early"


def test_patch_endpoint_rejects_bad_status(client):
    created = client.post("/api/reservations", json={
        "guest_name": "Annie Easley", "phone": "+15550177", "party_size": 2,
        "when": _friday_7pm_iso(),
    }).json()
    res = client.patch(f"/api/reservations/{created['confirmation_code']}",
                       json={"status": "enroute"})
    assert res.status_code == 422


def test_patch_endpoint_unknown_code_is_404(client):
    res = client.patch("/api/reservations/NOPE99", json={"status": "seated"})
    assert res.status_code == 404


def test_source_defaults_to_manual_and_can_be_overridden(client):
    base = {"guest_name": "Src Test", "phone": "+15550001", "party_size": 2}
    d = _friday_7pm_iso()

    made = client.post("/api/reservations", json={**base, "when": d}).json()
    assert made["source"] == "manual"  # a dashboard booking, not "api"

    d2 = d.replace("T19:00:00", "T19:30:00")
    made2 = client.post("/api/reservations", json={**base, "when": d2, "source": "voice"}).json()
    assert made2["source"] == "voice"

    d3 = d.replace("T19:00:00", "T20:00:00")
    bad = client.post("/api/reservations", json={**base, "when": d3, "source": "carrier-pigeon"})
    assert bad.status_code == 422


def test_free_text_when_is_accepted(client):
    res = client.post("/api/reservations", json={
        "guest_name": "Free Text", "phone": "+15550142", "party_size": 2,
        "when": "next Friday at 7pm",
    })
    # The free-text date must parse (not 422); booking itself may 201 or 409.
    assert res.status_code in (201, 409), res.text


# --- GET /api/availability/day (openings strip) ------------------------------

def test_day_availability_open_day(client):
    d = _next_weekday_date(4)  # a Friday
    res = client.get("/api/availability/day", params={"date": d, "party_size": 2}).json()
    assert res["reason"] is None
    assert res["slot_minutes"] == 15
    assert res["windows"] and res["windows"][0]["open"] == "17:00"
    assert len(res["slots"]) > 0
    assert res["slots"][0]["bookable"] is True
    assert res["slots"][0]["free_tables"] == 14  # nothing booked in the test db


def test_day_availability_closed_monday(client):
    d = _next_weekday_date(0)  # a Monday — restaurant is closed
    res = client.get("/api/availability/day", params={"date": d, "party_size": 2}).json()
    assert res["reason"] == "closed"
    assert res["slots"] == []
    assert res["next_open_date"] is not None  # points at the next open day


def test_day_availability_party_too_large(client):
    d = _next_weekday_date(4)
    res = client.get("/api/availability/day", params={"date": d, "party_size": 12}).json()
    assert res["reason"] == "party_too_large"
    assert res["slots"] == []
    assert res["next_open_date"] is None  # no future date helps an oversized party
