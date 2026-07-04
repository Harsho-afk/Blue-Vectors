"""
ARIA — Auth utilities
Password hashing, JWT encode/decode, FastAPI dependency.
Consistent with collector.py raw-SQL / psycopg2 pattern.
"""

import os
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Cookie, HTTPException, status
from jose import JWTError, jwt
import bcrypt

# ── Config from env ───────────────────────────────────────────────────────────

JWT_SECRET: str = os.environ.get("JWT_SECRET", "dev-secret-change-in-prod")
JWT_ALGORITHM: str = os.environ.get("JWT_ALGORITHM", "HS256")
JWT_EXPIRE_MINUTES: int = int(os.environ.get("JWT_EXPIRE_MINUTES", "1440"))

# ── Database setup ────────────────────────────────────────────────────────────
# For dev: SQLite. For prod: uncomment psycopg2 and set DATABASE_URL env var.

DB_TYPE = os.environ.get("DB_TYPE", "sqlite")  # "sqlite" or "postgres"
DB_PATH = os.environ.get("DB_PATH", "aria.db")  # SQLite file path

def _init_db():
    """Initialize SQLite database with all required tables."""
    if DB_TYPE != "sqlite":
        return  # PostgreSQL assumes schema.sql already applied
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    # 1. users
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            full_name TEXT,
            role TEXT NOT NULL DEFAULT 'investigator',
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # 2. cases
    cur.execute("""
        CREATE TABLE IF NOT EXISTS cases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            investigator_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            title TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'closed')),
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            closed_at TIMESTAMP
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_cases_investigator_id ON cases(investigator_id)")
    
    # 3. case_identifiers
    cur.execute("""
        CREATE TABLE IF NOT EXISTS case_identifiers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id INTEGER NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
            identifier_type TEXT NOT NULL CHECK (identifier_type IN ('username', 'email', 'phone', 'profile_url')),
            value TEXT NOT NULL,
            platform_hint TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_case_identifiers_case_id ON case_identifiers(case_id)")
    
    # 4. accounts
    cur.execute("""
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id INTEGER REFERENCES cases(id) ON DELETE CASCADE,
            platform TEXT NOT NULL,
            username TEXT NOT NULL,
            display_name TEXT,
            bio TEXT,
            location TEXT,
            created_at TIMESTAMP,
            profile_image_url TEXT,
            UNIQUE (case_id, platform, username)
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_accounts_case_id ON accounts(case_id)")
    
    # 5. posts
    cur.execute("""
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
            text TEXT,
            timestamp TIMESTAMP NOT NULL,
            metadata TEXT,
            spike_flag BOOLEAN NOT NULL DEFAULT 0,
            UNIQUE (account_id, timestamp, text)
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_posts_account_id ON posts(account_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_posts_timestamp ON posts(timestamp)")
    
    # 6. osint_lookups
    cur.execute("""
        CREATE TABLE IF NOT EXISTS osint_lookups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id INTEGER NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
            lookup_type TEXT NOT NULL CHECK (lookup_type IN ('sherlock', 'hibp', 'profile_url_scrape')),
            input_value TEXT NOT NULL,
            result_json TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_osint_lookups_case_id ON osint_lookups(case_id)")
    
    # 7. linkage_results
    cur.execute("""
        CREATE TABLE IF NOT EXISTS linkage_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id INTEGER NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
            account_a_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
            account_b_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
            confidence REAL NOT NULL,
            shap_json TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT linkage_results_ordered_accounts CHECK (account_a_id < account_b_id)
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_linkage_results_case_id ON linkage_results(case_id)")
    
    conn.commit()
    conn.close()

_init_db()

# ── Password hashing ──────────────────────────────────────────────────────────

_BCRYPT_MAX_BYTES = 72  # bcrypt's hard limit — enforce explicitly rather than relying on the library to truncate


def hash_password(plain: str) -> str:
    """Return a bcrypt hash of *plain*, stored as a UTF-8 string."""
    encoded = plain.encode("utf-8")
    if len(encoded) > _BCRYPT_MAX_BYTES:
        raise ValueError(f"Password must be at most {_BCRYPT_MAX_BYTES} bytes")
    return bcrypt.hashpw(encoded, bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Return True if *plain* matches the stored bcrypt *hashed* value."""
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        # Malformed/unsupported hash string in the DB
        return False


# ── JWT encode / decode ───────────────────────────────────────────────────────

def create_access_token(user_id: int, email: str) -> str:
    """
    Encode a signed JWT with sub=user_id, email, and exp.
    Expiry is controlled by JWT_EXPIRE_MINUTES (.env).
    """
    expire = datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRE_MINUTES)
    payload = {
        "sub": str(user_id),
        "email": email,
        "exp": expire,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    """
    Decode and verify a JWT.
    Raises jose.JWTError on expiry or invalid signature.
    """
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])


# ── Database connection helper ────────────────────────────────────────────────

def get_db_conn():
    """
    Open a database connection (SQLite for dev, PostgreSQL for prod).
    
    SQLite: Uses aria.db file in current directory
    PostgreSQL: Requires DATABASE_URL env var (postgresql://user:pass@host:port/db)
    """
    if DB_TYPE == "sqlite":
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn
    else:
        # PostgreSQL fallback (for production)
        try:
            import psycopg2
            import psycopg2.extras
        except ImportError:
            raise RuntimeError("psycopg2 not installed. For PostgreSQL, run: pip install psycopg2-binary")
        
        url = os.environ.get("DATABASE_URL")
        if url:
            return psycopg2.connect(url, cursor_factory=psycopg2.extras.RealDictCursor)
        
        return psycopg2.connect(
            host=os.environ.get("PGHOST", "localhost"),
            port=int(os.environ.get("PGPORT", "5432")),
            dbname=os.environ.get("PGDATABASE", "aria"),
            user=os.environ.get("PGUSER", "postgres"),
            password=os.environ.get("PGPASSWORD", ""),
            cursor_factory=psycopg2.extras.RealDictCursor,
        )


# ── FastAPI dependency ────────────────────────────────────────────────────────

def get_current_user(aria_token: Optional[str] = Cookie(default=None)) -> dict:
    """
    FastAPI dependency.  Reads the HttpOnly cookie 'aria_token', decodes the
    JWT, looks up the user row, and returns it.

    Usage in a route:
        current_user = Depends(get_current_user)
    """
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
    )
    if not aria_token:
        raise credentials_exc

    try:
        payload = decode_access_token(aria_token)
        user_id: Optional[str] = payload.get("sub")
        if user_id is None:
            raise credentials_exc
    except JWTError:
        raise credentials_exc

    conn = get_db_conn()
    try:
        cur = conn.cursor()
        if DB_TYPE == "sqlite":
            cur.execute("SELECT id, email, full_name, role FROM users WHERE id = ?", (int(user_id),))
        else:
            cur.execute("SELECT id, email, full_name, role FROM users WHERE id = %s", (int(user_id),))
        user = cur.fetchone()
    finally:
        conn.close()

    if user is None:
        raise credentials_exc

    return dict(user)
