import os
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import Cookie, HTTPException, status
from jose import JWTError, jwt
import bcrypt
import psycopg2
import psycopg2.extras

JWT_SECRET: str = os.environ.get("JWT_SECRET", "dev-secret-change-in-prod")
JWT_ALGORITHM: str = os.environ.get("JWT_ALGORITHM", "HS256")
JWT_EXPIRE_MINUTES: int = int(os.environ.get("JWT_EXPIRE_MINUTES", "1440"))

BCRYPT_MAX_BYTES = 72


def hash_password(plain: str) -> str:
    encoded = plain.encode("utf-8")
    if len(encoded) > BCRYPT_MAX_BYTES:
        raise ValueError(f"Password must be at most {BCRYPT_MAX_BYTES} bytes")
    return bcrypt.hashpw(encoded, bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(user_id: int, email: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRE_MINUTES)
    payload = {
        "sub": str(user_id),
        "email": email,
        "exp": expire,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])


def get_db_conn():
    database_url = os.environ.get("DATABASE_URL")

    if not database_url:
        raise RuntimeError("DATABASE_URL environment variable not set")

    return psycopg2.connect(
        database_url,
        cursor_factory=psycopg2.extras.RealDictCursor,
    )


def get_current_user(aria_token: Optional[str] = Cookie(default=None)) -> dict:
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
    )

    if not aria_token:
        raise credentials_exc

    try:
        payload = decode_access_token(aria_token)
        user_id = payload.get("sub")

        if user_id is None:
            raise credentials_exc

    except JWTError:
        raise credentials_exc

    conn = get_db_conn()

    try:
        cur = conn.cursor()

        cur.execute(
            """
            SELECT id, email, full_name, role
            FROM users
            WHERE id = %s
            """,
            (int(user_id),),
        )

        user = cur.fetchone()

    finally:
        conn.close()

    if user is None:
        raise credentials_exc

    return dict(user)
