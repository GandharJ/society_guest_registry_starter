import os

# Settings() is built at import time, so configure the environment first.
os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production-0123456789")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app

PASSWORD = "a-long-test-password"


@pytest.fixture()
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()
    engine.dispose()


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def login(client, email, password=PASSWORD):
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return auth(r.json()["access_token"])


def make_society(client, admin_email="admin@example.com", name="Demo", flats=("A-101",)):
    """Bootstrap (first call only) or log in an admin, then build society + flats."""
    r = client.post("/auth/register", json={"name": "Admin", "email": admin_email,
                                            "password": PASSWORD, "role": "admin"})
    assert r.status_code == 201, r.text
    h = login(client, admin_email)
    assert client.post("/admin/societies", json={"name": name}, headers=h).status_code == 201
    b = client.post("/admin/buildings", json={"name": "A"}, headers=h).json()
    for f in flats:
        assert client.post("/admin/flats", json={"building_id": b["id"], "flat_number": f},
                           headers=h).status_code == 201
    return h


def add_user(client, admin_headers, email, role, flat=None):
    body = {"name": email.split("@")[0].title() + " User", "email": email,
            "password": PASSWORD, "role": role}
    if flat:
        body["flat_number"] = flat
    r = client.post("/admin/users", json=body, headers=admin_headers)
    assert r.status_code == 201, r.text
    return login(client, email)


@pytest.fixture()
def society(client):
    admin = make_society(client, flats=("A-101", "A-102"))
    guard = add_user(client, admin, "guard@example.com", "guard")
    resident = add_user(client, admin, "res101@example.com", "resident", "A-101")
    other_resident = add_user(client, admin, "res102@example.com", "resident", "A-102")
    return {"admin": admin, "guard": guard, "resident": resident, "other": other_resident}


def new_visitor(client, guard, flat="A-101"):
    r = client.post("/visitors", json={"name": "Sam Visitor", "mobile": "9999999999",
                                       "flat_number": flat, "purpose": "Delivery"}, headers=guard)
    assert r.status_code == 201, r.text
    return r.json()


def approved_visitor(client, s, flat="A-101"):
    v = new_visitor(client, s["guard"], flat)
    who = s["resident"] if flat == "A-101" else s["other"]
    r = client.post(f"/visitors/{v['id']}/decision", json={"approved": True}, headers=who)
    assert r.status_code == 200, r.text
    return v
