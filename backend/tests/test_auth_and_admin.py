from .conftest import PASSWORD, add_user, auth, login, make_society


def test_bootstrap_only_once_and_must_be_admin(client):
    r = client.post("/auth/register", json={"name": "Nope", "email": "g@example.com",
                                            "password": PASSWORD, "role": "guard"})
    assert r.status_code == 400
    ok = {"name": "Admin", "email": "a@example.com", "password": PASSWORD, "role": "admin"}
    assert client.post("/auth/register", json=ok).status_code == 201
    ok["email"] = "b@example.com"
    assert client.post("/auth/register", json=ok).status_code == 403


def test_login_wrong_password_and_case_insensitive_email(client):
    client.post("/auth/register", json={"name": "Admin", "email": "Admin@Example.com",
                                        "password": PASSWORD, "role": "admin"})
    assert client.post("/auth/login", json={"email": "admin@example.com",
                                            "password": "wrong-password-1"}).status_code == 401
    assert client.post("/auth/login", json={"email": "ADMIN@EXAMPLE.COM",
                                            "password": PASSWORD}).status_code == 200


def test_requires_token(client):
    assert client.get("/visitors").status_code in (401, 403)
    assert client.get("/visitors", headers=auth("garbage")).status_code == 401


def test_admin_can_only_link_one_society(client):
    h = make_society(client)
    assert client.post("/admin/societies", json={"name": "Second"}, headers=h).status_code == 409


def test_non_admin_cannot_use_admin_endpoints(client, society):
    r = client.post("/admin/users", headers=society["guard"], json={
        "name": "Evil", "email": "evil@example.com", "password": PASSWORD, "role": "admin"})
    assert r.status_code == 403
    assert client.get("/admin/users", headers=society["resident"]).status_code == 403


def test_resident_requires_existing_flat(client, society):
    base = {"name": "Res", "password": PASSWORD, "role": "resident"}
    r = client.post("/admin/users", headers=society["admin"],
                    json={**base, "email": "x@example.com"})
    assert r.status_code == 400  # no flat number
    r = client.post("/admin/users", headers=society["admin"],
                    json={**base, "email": "y@example.com", "flat_number": "Z-999"})
    assert r.status_code == 400  # flat does not exist


def test_duplicate_email_rejected(client, society):
    r = client.post("/admin/users", headers=society["admin"], json={
        "name": "Dup", "email": "GUARD@example.com", "password": PASSWORD, "role": "guard"})
    assert r.status_code == 409


def test_flat_must_belong_to_admins_building(client):
    h = make_society(client)
    r = client.post("/admin/flats", json={"building_id": 9999, "flat_number": "Q-1"}, headers=h)
    assert r.status_code == 404


def test_duplicate_flat_rejected(client):
    h = make_society(client, flats=("A-101",))
    r = client.post("/admin/flats", json={"building_id": 1, "flat_number": "A-101"}, headers=h)
    assert r.status_code == 409
