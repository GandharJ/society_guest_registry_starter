from datetime import datetime, timedelta, timezone
from hashlib import sha256

from sqlalchemy import select

from app.database import get_db
from app.main import app
from app.models import QRPass
from .conftest import PASSWORD, add_user, approved_visitor, make_society, new_visitor


def test_full_flow_guard_resident_checkin_checkout(client, society):
    v = new_visitor(client, society["guard"])
    assert v["status"] == "pending"
    # Guard cannot check in before approval, nor approve themself
    assert client.post(f"/visitors/{v['id']}/check-in", headers=society["guard"]).status_code == 409
    assert client.post(f"/visitors/{v['id']}/decision", json={"approved": True},
                       headers=society["guard"]).status_code == 403
    r = client.post(f"/visitors/{v['id']}/decision", json={"approved": True},
                    headers=society["resident"])
    assert r.json()["status"] == "approved"
    # Decision is final
    assert client.post(f"/visitors/{v['id']}/decision", json={"approved": False},
                       headers=society["resident"]).status_code == 409
    assert client.post(f"/visitors/{v['id']}/check-in",
                       headers=society["guard"]).json()["status"] == "inside"
    assert client.post(f"/visitors/{v['id']}/check-out",
                       headers=society["guard"]).json()["status"] == "exited"
    assert client.post(f"/visitors/{v['id']}/check-out", headers=society["guard"]).status_code == 409


def test_visitor_for_unknown_flat_rejected(client, society):
    r = client.post("/visitors", headers=society["guard"], json={
        "name": "Sam", "mobile": "9999999999", "flat_number": "Z-9", "purpose": "Visit"})
    assert r.status_code == 400


def test_resident_only_sees_and_decides_own_flat(client, society):
    v = new_visitor(client, society["guard"], "A-101")
    assert [x["id"] for x in client.get("/visitors", headers=society["resident"]).json()] == [v["id"]]
    assert client.get("/visitors", headers=society["other"]).json() == []
    r = client.post(f"/visitors/{v['id']}/decision", json={"approved": True}, headers=society["other"])
    assert r.status_code == 403
    # resident supplying someone else's flat in the filter still only gets own flat
    assert client.get("/visitors?flat_number=A-101", headers=society["other"]).json() == []


def test_resident_cannot_register_visitors_or_check_in(client, society):
    r = client.post("/visitors", headers=society["resident"], json={
        "name": "Sam", "mobile": "9999999999", "flat_number": "A-101", "purpose": "Visit"})
    assert r.status_code == 403
    v = approved_visitor(client, society)
    assert client.post(f"/visitors/{v['id']}/check-in", headers=society["resident"]).status_code == 403


def test_tenant_isolation_between_societies(client, society):
    v = new_visitor(client, society["guard"])
    # A second society's staff, created directly in the DB (bootstrap is one-shot)
    from app.models import Society, User
    from app.security import hash_password
    db = next(app.dependency_overrides[get_db]())
    other = Society(name="Other"); db.add(other); db.flush()
    db.add(User(name="Other Guard", email="og@example.com", role="guard",
                password_hash=hash_password(PASSWORD), society_id=other.id))
    db.commit(); db.close()
    from .conftest import login
    og = login(client, "og@example.com")
    assert client.get("/visitors", headers=og).json() == []
    for path in ("check-in", "check-out", "qr-pass"):
        assert client.post(f"/visitors/{v['id']}/{path}", headers=og).status_code == 404
    assert client.get("/dashboard/summary", headers=og).json()["total"] == 0


def test_user_without_society_gets_nothing(client):
    # bootstrap admin has no society until one is created; must not see orphan rows
    client.post("/auth/register", json={"name": "Admin", "email": "a@example.com",
                                        "password": PASSWORD, "role": "admin"})
    from .conftest import login
    h = login(client, "a@example.com")
    assert client.get("/visitors", headers=h).status_code == 400
    assert client.get("/dashboard/summary", headers=h).status_code == 400


def test_dashboard_summary_counts(client, society):
    approved_visitor(client, society)
    new_visitor(client, society["guard"], "A-102")
    s = client.get("/dashboard/summary", headers=society["admin"]).json()
    assert s == {"total": 2, "pending": 1, "inside": 0, "exited": 0}
    assert client.get("/dashboard/summary", headers=society["other"]).json()["total"] == 1


def issue(client, s, vid):
    r = client.post(f"/visitors/{vid}/qr-pass", headers=s["guard"])
    assert r.status_code == 200, r.text
    return r.json()["qr_token"]


def test_qr_requires_approval(client, society):
    v = new_visitor(client, society["guard"])
    assert client.post(f"/visitors/{v['id']}/qr-pass", headers=society["guard"]).status_code == 409


def test_qr_single_use(client, society):
    v = approved_visitor(client, society)
    token = issue(client, society, v["id"])
    r = client.post(f"/gate/scan/{token}", headers=society["guard"])
    assert r.status_code == 200 and r.json()["status"] == "inside"
    assert client.post(f"/gate/scan/{token}", headers=society["guard"]).status_code == 400


def test_qr_unknown_token_and_residents_cannot_scan(client, society):
    assert client.post("/gate/scan/not-a-token", headers=society["guard"]).status_code == 400
    v = approved_visitor(client, society)
    token = issue(client, society, v["id"])
    assert client.post(f"/gate/scan/{token}", headers=society["resident"]).status_code == 403


def test_qr_only_hash_stored(client, society):
    v = approved_visitor(client, society)
    token = issue(client, society, v["id"])
    db = next(app.dependency_overrides[get_db]())
    rows = db.scalars(select(QRPass)).all()
    assert [r.token_hash for r in rows] == [sha256(token.encode()).hexdigest()]
    db.close()


def test_qr_expired(client, society):
    v = approved_visitor(client, society)
    token = issue(client, society, v["id"])
    db = next(app.dependency_overrides[get_db]())
    p = db.scalar(select(QRPass))
    p.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db.commit(); db.close()
    assert client.post(f"/gate/scan/{token}", headers=society["guard"]).status_code == 400


def test_new_pass_voids_old_one(client, society):
    v = approved_visitor(client, society)
    old = issue(client, society, v["id"])
    new = issue(client, society, v["id"])
    assert client.post(f"/gate/scan/{old}", headers=society["guard"]).status_code == 400
    assert client.post(f"/gate/scan/{new}", headers=society["guard"]).status_code == 200


def test_manual_checkin_voids_outstanding_pass(client, society):
    v = approved_visitor(client, society)
    token = issue(client, society, v["id"])
    assert client.post(f"/visitors/{v['id']}/check-in", headers=society["guard"]).status_code == 200
    assert client.post(f"/gate/scan/{token}", headers=society["guard"]).status_code == 400


def test_csv_report_access_and_formula_injection(client, society):
    r = client.post("/visitors", headers=society["guard"], json={
        "name": "=HYPERLINK(\"http://evil\")", "mobile": "9999999999",
        "flat_number": "A-101", "purpose": "Visit"})
    assert r.status_code == 201
    assert client.get("/reports/visitors.csv", headers=society["resident"]).status_code == 403
    csv_text = client.get("/reports/visitors.csv", headers=society["admin"]).text
    assert "'=HYPERLINK" in csv_text
    assert ",=HYPERLINK" not in csv_text
