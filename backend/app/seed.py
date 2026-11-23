"""Create a small, idempotent set of development data.

Run inside the API container:

    SEED_PASSWORD='a-long-dev-password' docker compose exec -e SEED_PASSWORD api python -m app.seed

Creates one society, one building, one flat, and an admin, a guard and a resident
account, all sharing SEED_PASSWORD (min 10 chars). Safe to run more than once.
Development only: never seed shared passwords into a real deployment.
"""
import os
import sys
from sqlalchemy import select
from .database import Base, engine, SessionLocal
from .models import Society, Building, Flat, User
from .security import hash_password

ACCOUNTS = [
    ("Dev Admin", "admin@example.com", "admin", None),
    ("Dev Guard", "guard@example.com", "guard", None),
    ("Dev Resident", "resident@example.com", "resident", "A-101"),
]

def main() -> None:
    password = os.environ.get("SEED_PASSWORD", "")
    if len(password) < 10:
        sys.exit("Set SEED_PASSWORD to a password of at least 10 characters.")

    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        society = db.scalar(select(Society).where(Society.name == "Demo Society"))
        if not society:
            society = Society(name="Demo Society", address="1 Example Road")
            db.add(society); db.flush()

        building = db.scalar(select(Building).where(
            Building.society_id == society.id, Building.name == "A"))
        if not building:
            building = Building(society_id=society.id, name="A")
            db.add(building); db.flush()

        if not db.scalar(select(Flat).where(
                Flat.building_id == building.id, Flat.flat_number == "A-101")):
            db.add(Flat(society_id=society.id, building_id=building.id, flat_number="A-101"))

        for name, email, role, flat in ACCOUNTS:
            if not db.scalar(select(User).where(User.email == email)):
                db.add(User(name=name, email=email, password_hash=hash_password(password),
                            role=role, flat_number=flat, society_id=society.id))
        db.commit()

    print("Seeded. Log in as admin@example.com, guard@example.com or resident@example.com.")

if __name__ == "__main__":
    main()
