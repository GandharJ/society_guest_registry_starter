from datetime import datetime
from pydantic import BaseModel, EmailStr, Field, ConfigDict

class RegisterIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    role: str
    flat_number: str | None = None

class LoginIn(BaseModel):
    email: EmailStr
    password: str

class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"

class VisitorCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    mobile: str = Field(min_length=8, max_length=20)
    flat_number: str = Field(min_length=1, max_length=30)
    purpose: str = Field(min_length=2, max_length=200)
    vehicle_number: str | None = Field(default=None, max_length=30)

class DecisionIn(BaseModel):
    approved: bool
    note: str | None = None

class VisitorOut(BaseModel):
    id: int
    name: str
    mobile: str
    flat_number: str
    purpose: str
    vehicle_number: str | None
    status: str
    entry_time: datetime | None
    exit_time: datetime | None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)
