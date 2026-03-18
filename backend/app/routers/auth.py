from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pymongo.errors import DuplicateKeyError

from app.database import users_collection
from app.schemas import AuthResponse, LoginRequest, RegisterRequest
from app.utils.security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register_user(payload: RegisterRequest) -> AuthResponse:
    existing_user = users_collection.find_one({"email": payload.email.lower()})
    if existing_user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")

    user_document = {
        "name": payload.name,
        "email": payload.email.lower(),
        "password": hash_password(payload.password),
    }

    try:
        users_collection.insert_one(user_document)
    except DuplicateKeyError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered") from exc

    token = create_access_token({"email": user_document["email"]})
    return AuthResponse(
        message="Registration successful",
        access_token=token,
        user={"name": user_document["name"], "email": user_document["email"]},
    )


@router.post("/login", response_model=AuthResponse)
def login_user(payload: LoginRequest) -> AuthResponse:
    user = users_collection.find_one({"email": payload.email.lower()})
    if not user or not verify_password(payload.password, user["password"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    token = create_access_token({"email": user["email"]})
    return AuthResponse(
        message="Login successful",
        access_token=token,
        user={"name": user["name"], "email": user["email"]},
    )
