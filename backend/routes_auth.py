"""
ARIA — Auth routes
POST /api/auth/register
POST /api/auth/login
POST /api/auth/logout
GET  /api/auth/me
"""
import os
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, EmailStr, field_validator
from auth import (
    create_access_token,
    get_current_user,
    get_db_conn,
    hash_password,
    verify_password,
    JWT_EXPIRE_MINUTES,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


# ── Pydantic models ───────────────────────────────────────────────────────────
class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: Optional[str] = None

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


# ── Cookie helper ─────────────────────────────────────────────────────────────
# TODO (prod): set secure=True when serving over HTTPS
_COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "false").lower() == "true"
_COOKIE_NAME = "aria_token"


def set_auth_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=_COOKIE_SECURE,  # False for local http dev; True in prod
        samesite="lax",
        max_age=JWT_EXPIRE_MINUTES * 60,
    )


# ── Routes ────────────────────────────────────────────────────────────────────
@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest, response: Response):
    """
    Create a new user account and issue an auth cookie.
    Returns 409 if the email is already registered.
    """
    conn = get_db_conn()
    try:
        cur = conn.cursor()

        # Check for duplicate
        cur.execute("SELECT id FROM users WHERE email = %s", (body.email,))

        if cur.fetchone():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email already registered",
            )

        pw_hash = hash_password(body.password)

        cur.execute(
            """
            INSERT INTO users (email, password_hash, full_name)
            VALUES (%s, %s, %s)
            RETURNING id, email, full_name, role
            """,
            (body.email, pw_hash, body.full_name),
        )
        conn.commit()

        user = dict(cur.fetchone())
    finally:
        conn.close()

    token = create_access_token(user["id"], user["email"])
    set_auth_cookie(response, token)
    return {
        "id": user["id"],
        "email": user["email"],
        "full_name": user["full_name"],
        "role": user["role"],
    }


@router.post("/login")
def login(body: LoginRequest, response: Response):
    """
    Authenticate with email + password and issue an auth cookie.
    Returns 401 on wrong credentials (intentionally vague message).
    """
    conn = get_db_conn()
    try:
        cur = conn.cursor()

        cur.execute(
            "SELECT id, email, password_hash, full_name, role FROM users WHERE email = %s",
            (body.email,),
        )

        user = cur.fetchone()
    finally:
        conn.close()

    _invalid = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid email or password",
    )
    if user is None:
        raise _invalid
    if not verify_password(body.password, user["password_hash"]):
        raise _invalid

    token = create_access_token(user["id"], user["email"])
    set_auth_cookie(response, token)
    return {
        "id": user["id"],
        "email": user["email"],
        "full_name": user["full_name"],
        "role": user["role"],
    }


@router.post("/logout")
def logout(response: Response):
    """Delete the auth cookie (client-side session ends)."""
    response.delete_cookie(key=_COOKIE_NAME, httponly=True, samesite="lax")
    return {"detail": "Logged out"}


@router.get("/me")
def me(current_user: dict = Depends(get_current_user)):
    """
    Return the currently authenticated user.
    Used by the frontend on app load to restore session state.
    Returns 401 if no valid cookie present.
    """
    return current_user


class UpdateProfileRequest(BaseModel):
    full_name: str


@router.put("/profile")
def update_profile(body: UpdateProfileRequest, current_user: dict = Depends(get_current_user)):
    """
    Update the full name (investigator name) of the currently logged-in user.
    """
    name_clean = body.full_name.strip()
    if len(name_clean) < 2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Name must be at least 2 characters",
        )
    conn = get_db_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE users
            SET full_name = %s
            WHERE id = %s
            RETURNING id, email, full_name, role
            """,
            (name_clean, current_user["id"]),
        )
        conn.commit()
        updated = cur.fetchone()
        if not updated:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )
        updated_user = dict(updated)
    finally:
        conn.close()
    return updated_user

