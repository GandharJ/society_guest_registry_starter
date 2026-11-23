from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
from hashlib import sha256
import secrets
import csv
import io
from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import select, desc, func, delete, update
from .database import Base, engine, get_db
from .models import User, Visitor, Society, Building, Flat, QRPass
from .schemas import UserCreate, LoginIn, TokenOut, UserOut, VisitorCreate, VisitorOut, DecisionIn, SocietyCreate, BuildingCreate, FlatCreate
from .security import hash_password, verify_password, create_token, current_user, require_roles

@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield

app = FastAPI(title="Society Guest Registry API", version="0.3.0", lifespan=lifespan)

def _aware(dt: datetime) -> datetime:
    """Some databases (e.g. SQLite) return naive datetimes; treat them as UTC."""
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

def _require_society(user: User) -> int:
    if not user.society_id:
        raise HTTPException(400, "Your account is not linked to a society yet.")
    return user.society_id

def _flat_exists(db: Session, society_id: int, flat_number: str) -> bool:
    return db.scalar(select(Flat.id).where(Flat.society_id == society_id,
                                           Flat.flat_number == flat_number,
                                           Flat.is_active.is_(True)).limit(1)) is not None

def _get_visit(db: Session, user: User, visitor_id: int) -> Visitor:
    """Fetch a visitor, scoped to the caller's society (404 otherwise, never leak existence)."""
    visit = db.get(Visitor, visitor_id)
    if not user.society_id or not visit or visit.society_id != user.society_id:
        raise HTTPException(404, "Visitor not found.")
    return visit

def _void_open_passes(db: Session, visitor_id: int) -> None:
    db.execute(delete(QRPass).where(QRPass.visitor_id == visitor_id, QRPass.used_at.is_(None)))

def _csv_safe(value):
    """Neutralise spreadsheet formula injection in user-supplied text."""
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/auth/register", response_model=UserOut, status_code=201)
def bootstrap_admin(data: UserCreate, db: Session = Depends(get_db)):
    if db.scalar(select(func.count(User.id))) != 0:
        raise HTTPException(403, "Initial setup is complete; ask your society admin for an account.")
    if data.role != "admin":
        raise HTTPException(400, "First account must be an admin.")
    user = User(name=data.name, email=data.email, password_hash=hash_password(data.password),
                role="admin", flat_number=None, society_id=None)
    db.add(user); db.commit(); db.refresh(user)
    return user

@app.post("/auth/login", response_model=TokenOut)
def login(data: LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == data.email))
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(401, "Incorrect email or password.")
    return {"access_token": create_token(user), "role": user.role, "name": user.name,
            "flat_number": user.flat_number}

@app.get("/auth/me")
def me(user: User = Depends(current_user)):
    return {"id": user.id, "name": user.name, "email": user.email,
            "role": user.role, "flat_number": user.flat_number, "society_id": user.society_id}

@app.post("/admin/societies", status_code=201)
def create_society(data: SocietyCreate, db: Session = Depends(get_db),
                   admin: User = Depends(require_roles("admin"))):
    # An admin manages exactly one society. Creating a society links the admin to it,
    # so the building/flat/user endpoints below work without manual database edits.
    if admin.society_id:
        raise HTTPException(409, "Your account is already linked to a society.")
    society = Society(name=data.name, address=data.address)
    db.add(society); db.flush()
    admin.society_id = society.id
    db.commit(); db.refresh(society)
    return {"id": society.id, "name": society.name, "address": society.address}

@app.post("/admin/buildings", status_code=201)
def create_building(data: BuildingCreate, db: Session = Depends(get_db),
                    admin: User = Depends(require_roles("admin"))):
    if not admin.society_id:
        raise HTTPException(400, "Assign the administrator to a society before adding buildings.")
    building = Building(name=data.name, society_id=admin.society_id)
    db.add(building); db.commit(); db.refresh(building)
    return {"id": building.id, "name": building.name}

@app.post("/admin/flats", status_code=201)
def create_flat(data: FlatCreate, db: Session = Depends(get_db),
                admin: User = Depends(require_roles("admin"))):
    building = db.get(Building, data.building_id)
    if not building or building.society_id != admin.society_id:
        raise HTTPException(404, "Building not found in your society.")
    exists = db.scalar(select(Flat).where(Flat.building_id == data.building_id,
                                         Flat.flat_number == data.flat_number))
    if exists: raise HTTPException(409, "Flat already exists.")
    flat = Flat(society_id=admin.society_id, building_id=data.building_id,
                flat_number=data.flat_number)
    db.add(flat); db.commit(); db.refresh(flat)
    return {"id": flat.id, "building_id": flat.building_id, "flat_number": flat.flat_number}

@app.post("/admin/users", response_model=UserOut, status_code=201)
def create_user(data: UserCreate, db: Session = Depends(get_db),
                admin: User = Depends(require_roles("admin"))):
    if data.role not in {"admin", "guard", "resident"}:
        raise HTTPException(400, "Invalid role.")
    if data.role == "resident" and not data.flat_number:
        raise HTTPException(400, "Residents must have a flat number.")
    if db.scalar(select(User).where(User.email == data.email)):
        raise HTTPException(409, "Email already registered.")
    if not admin.society_id:
        raise HTTPException(400, "Create your society first (POST /admin/societies).")
    society_id = admin.society_id
    if data.role == "resident" and not _flat_exists(db, society_id, data.flat_number):
        raise HTTPException(400, "Flat not found in your society; create it first (POST /admin/flats).")
    user = User(name=data.name, email=data.email, password_hash=hash_password(data.password),
                role=data.role, flat_number=data.flat_number if data.role == "resident" else None,
                society_id=society_id)
    db.add(user); db.commit(); db.refresh(user)
    return user

@app.get("/admin/users", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), admin: User = Depends(require_roles("admin"))):
    return list(db.scalars(select(User).where(User.society_id == _require_society(admin)).order_by(User.role, User.name)).all())

@app.post("/visitors", response_model=VisitorOut, status_code=201)
def create_visitor(data: VisitorCreate, db: Session = Depends(get_db),
                   user: User = Depends(require_roles("guard", "admin"))):
    society_id = _require_society(user)
    if not _flat_exists(db, society_id, data.flat_number):
        raise HTTPException(400, "Unknown flat number for this society.")
    visit = Visitor(**data.model_dump(), created_by=user.id, status="pending",
                    society_id=society_id)
    db.add(visit); db.commit(); db.refresh(visit)
    # Configure Firebase Admin SDK and dispatch a push notification to the flat resident.
    return visit

@app.get("/visitors", response_model=list[VisitorOut])
def list_visitors(status: str | None = Query(default=None),
                  flat_number: str | None = Query(default=None),
                  db: Session = Depends(get_db), user: User = Depends(current_user)):
    stmt = select(Visitor).where(Visitor.society_id == _require_society(user)).order_by(desc(Visitor.created_at))
    if status: stmt = stmt.where(Visitor.status == status)
    if flat_number: stmt = stmt.where(Visitor.flat_number == flat_number)
    if user.role == "resident": stmt = stmt.where(Visitor.flat_number == user.flat_number)
    return list(db.scalars(stmt.limit(500)).all())

@app.post("/visitors/{visitor_id}/decision", response_model=VisitorOut)
def decision(visitor_id: int, data: DecisionIn, db: Session = Depends(get_db),
             user: User = Depends(require_roles("resident", "admin"))):
    visit = _get_visit(db, user, visitor_id)
    if user.role == "resident" and visit.flat_number != user.flat_number:
        raise HTTPException(403, "Visitor is not assigned to your flat.")
    if visit.status != "pending": raise HTTPException(409, "Decision already recorded.")
    visit.status = "approved" if data.approved else "rejected"
    visit.approved_by = user.id; visit.decision_note = data.note
    db.commit(); db.refresh(visit)
    # Configure FCM to notify the gate after a decision.
    return visit

@app.post("/visitors/{visitor_id}/qr-pass")
def issue_qr_pass(visitor_id: int, db: Session = Depends(get_db),
                  user: User = Depends(require_roles("guard", "admin"))):
    visit = _get_visit(db, user, visitor_id)
    if visit.status != "approved": raise HTTPException(409, "Only approved visitors can receive a pass.")
    if visit.entry_time: raise HTTPException(409, "Visitor is already checked in.")
    _void_open_passes(db, visit.id)  # only the newest pass for a visitor stays valid
    raw_token = secrets.token_urlsafe(32)
    token_hash = sha256(raw_token.encode()).hexdigest()
    pass_record = QRPass(visitor_id=visit.id, token_hash=token_hash,
                         expires_at=datetime.now(timezone.utc) + timedelta(hours=12))
    db.add(pass_record); db.commit()
    # Return raw token once; client can render it as a QR code. Store only its hash.
    return {"visitor_id": visit.id, "qr_token": raw_token,
            "expires_at": pass_record.expires_at.isoformat()}

@app.post("/gate/scan/{qr_token}", response_model=VisitorOut)
def scan_qr(qr_token: str, db: Session = Depends(get_db),
            user: User = Depends(require_roles("guard", "admin"))):
    society_id = _require_society(user)
    digest = sha256(qr_token.encode()).hexdigest()
    pass_record = db.scalar(select(QRPass).where(QRPass.token_hash == digest))
    now = datetime.now(timezone.utc)
    if not pass_record or pass_record.used_at or _aware(pass_record.expires_at) < now:
        raise HTTPException(400, "QR pass is invalid, expired or already used.")
    visit = db.get(Visitor, pass_record.visitor_id)
    if not visit or visit.society_id != society_id or visit.status != "approved":
        raise HTTPException(403, "Pass is not valid for this gate.")
    # Atomic single-use: only one concurrent scan can flip used_at from NULL.
    claimed = db.execute(update(QRPass).where(QRPass.id == pass_record.id, QRPass.used_at.is_(None))
                         .values(used_at=now)).rowcount
    if claimed != 1:
        db.rollback()
        raise HTTPException(400, "QR pass is invalid, expired or already used.")
    visit.status = "inside"; visit.entry_time = now
    db.commit(); db.refresh(visit)
    return visit

@app.post("/visitors/{visitor_id}/check-in", response_model=VisitorOut)
def check_in(visitor_id: int, db: Session = Depends(get_db),
             user: User = Depends(require_roles("guard", "admin"))):
    visit = _get_visit(db, user, visitor_id)
    if visit.status != "approved": raise HTTPException(409, "Resident approval is required.")
    visit.entry_time = datetime.now(timezone.utc); visit.status = "inside"
    _void_open_passes(db, visit.id)
    db.commit(); db.refresh(visit); return visit

@app.post("/visitors/{visitor_id}/check-out", response_model=VisitorOut)
def check_out(visitor_id: int, db: Session = Depends(get_db),
              user: User = Depends(require_roles("guard", "admin"))):
    visit = _get_visit(db, user, visitor_id)
    if visit.status != "inside": raise HTTPException(409, "Visitor is not currently inside.")
    visit.exit_time = datetime.now(timezone.utc); visit.status = "exited"
    db.commit(); db.refresh(visit); return visit

@app.get("/dashboard/summary")
def summary(db: Session = Depends(get_db), user: User = Depends(current_user)):
    stmt = select(Visitor).where(Visitor.society_id == _require_society(user))
    if user.role == "resident": stmt = stmt.where(Visitor.flat_number == user.flat_number)
    rows = list(db.scalars(stmt).all())
    return {"total": len(rows), "pending": sum(v.status == "pending" for v in rows),
            "inside": sum(v.status == "inside" for v in rows),
            "exited": sum(v.status == "exited" for v in rows)}

@app.get("/reports/visitors.csv")
def visitor_report(db: Session = Depends(get_db),
                   user: User = Depends(require_roles("admin", "guard"))):
    stmt = select(Visitor).where(Visitor.society_id == _require_society(user)).order_by(Visitor.created_at)
    rows = db.scalars(stmt).all()
    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerow(["Visitor ID", "Name", "Mobile", "Flat", "Purpose", "Status", "Entry Time", "Exit Time"])
    for v in rows:
        writer.writerow([_csv_safe(c) for c in
                         (v.id, v.name, v.mobile, v.flat_number, v.purpose, v.status, v.entry_time, v.exit_time)])
    stream.seek(0)
    return StreamingResponse(iter([stream.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=visitor_report.csv"})
