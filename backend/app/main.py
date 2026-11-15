from contextlib import asynccontextmanager
from datetime import datetime, timezone
from fastapi import FastAPI, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import select, desc
from .database import Base, engine, get_db
from .models import User, Visitor
from .schemas import RegisterIn, LoginIn, TokenOut, VisitorCreate, VisitorOut, DecisionIn
from .security import hash_password, verify_password, create_token, current_user, require_roles

@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)  # dev convenience; use Alembic in production
    yield

app = FastAPI(title="Society Guest Registry API", version="0.1.0", lifespan=lifespan)

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/auth/register", status_code=201)
def register(data: RegisterIn, db: Session = Depends(get_db)):
    # DEVELOPMENT ONLY: disable public registration in production.
    if data.role not in {"admin", "guard", "resident"}:
        raise HTTPException(400, "Invalid role")
    if data.role == "resident" and not data.flat_number:
        raise HTTPException(400, "Residents must have a flat number")
    if db.scalar(select(User).where(User.email == data.email)):
        raise HTTPException(409, "Email already registered")
    user = User(name=data.name, email=data.email, password_hash=hash_password(data.password),
                role=data.role, flat_number=data.flat_number)
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"id": user.id, "name": user.name, "role": user.role}

@app.post("/auth/login", response_model=TokenOut)
def login(data: LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == data.email))
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(401, "Incorrect email or password")
    return {"access_token": create_token(user)}

@app.post("/visitors", response_model=VisitorOut, status_code=201)
def create_visitor(data: VisitorCreate, db: Session = Depends(get_db),
                   user: User = Depends(require_roles("guard", "admin"))):
    visit = Visitor(**data.model_dump(), created_by=user.id, status="pending")
    db.add(visit)
    db.commit()
    db.refresh(visit)
    # TODO: send FCM notification to residents assigned to this flat.
    return visit

@app.get("/visitors", response_model=list[VisitorOut])
def list_visitors(
    status: str | None = Query(default=None),
    flat_number: str | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(current_user)
):
    stmt = select(Visitor).order_by(desc(Visitor.created_at))
    if status:
        stmt = stmt.where(Visitor.status == status)
    if flat_number:
        stmt = stmt.where(Visitor.flat_number == flat_number)
    # Residents can only see visits for their own flat.
    if user.role == "resident":
        stmt = stmt.where(Visitor.flat_number == user.flat_number)
    return list(db.scalars(stmt.limit(200)).all())

@app.post("/visitors/{visitor_id}/decision", response_model=VisitorOut)
def decide(visitor_id: int, data: DecisionIn, db: Session = Depends(get_db),
           user: User = Depends(require_roles("resident", "admin"))):
    visit = db.get(Visitor, visitor_id)
    if not visit:
        raise HTTPException(404, "Visitor not found")
    if user.role == "resident" and visit.flat_number != user.flat_number:
        raise HTTPException(403, "This visitor is not for your flat")
    if visit.status != "pending":
        raise HTTPException(409, "A decision has already been recorded")
    visit.status = "approved" if data.approved else "rejected"
    visit.approved_by = user.id
    visit.decision_note = data.note
    db.commit()
    db.refresh(visit)
    # TODO: notify gate guard through FCM/WebSocket.
    return visit

@app.post("/visitors/{visitor_id}/check-in", response_model=VisitorOut)
def check_in(visitor_id: int, db: Session = Depends(get_db),
             user: User = Depends(require_roles("guard", "admin"))):
    visit = db.get(Visitor, visitor_id)
    if not visit:
        raise HTTPException(404, "Visitor not found")
    if visit.status != "approved":
        raise HTTPException(409, "Visitor must be approved before check-in")
    if visit.entry_time:
        raise HTTPException(409, "Visitor is already checked in")
    visit.entry_time = datetime.now(timezone.utc)
    visit.status = "inside"
    db.commit()
    db.refresh(visit)
    return visit

@app.post("/visitors/{visitor_id}/check-out", response_model=VisitorOut)
def check_out(visitor_id: int, db: Session = Depends(get_db),
              user: User = Depends(require_roles("guard", "admin"))):
    visit = db.get(Visitor, visitor_id)
    if not visit:
        raise HTTPException(404, "Visitor not found")
    if visit.status != "inside":
        raise HTTPException(409, "Visitor is not currently inside")
    visit.exit_time = datetime.now(timezone.utc)
    visit.status = "exited"
    db.commit()
    db.refresh(visit)
    return visit
