import os
import hmac
import hashlib
import json
import base64
import time
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User

SECRET_KEY = os.environ.get("SECRET_KEY", "cambodia-people-census-secret-key-2026")
ALGORITHM = "HS256"
security = HTTPBearer(auto_error=False)


def hash_password(password: str, salt: Optional[bytes] = None) -> str:
    if salt is None:
        salt = os.urandom(16)
    hashed = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100_000)
    return f"{base64.b64encode(salt).decode('utf-8')}${base64.b64encode(hashed).decode('utf-8')}"


def verify_password(plain_password: str, hashed_str: str) -> bool:
    try:
        salt_b64, hash_b64 = hashed_str.split("$")
        salt = base64.b64decode(salt_b64.encode("utf-8"))
        expected_hash = base64.b64decode(hash_b64.encode("utf-8"))
        calculated_hash = hashlib.pbkdf2_hmac("sha256", plain_password.encode("utf-8"), salt, 100_000)
        return hmac.compare_digest(expected_hash, calculated_hash)
    except Exception:
        return False


def create_access_token(data: dict, expires_seconds: int = 86400 * 7) -> str:
    payload = data.copy()
    payload["exp"] = int(time.time()) + expires_seconds
    
    header = {"alg": ALGORITHM, "typ": "JWT"}
    header_bytes = base64.urlsafe_b64encode(json.dumps(header).encode("utf-8")).rstrip(b"=")
    payload_bytes = base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).rstrip(b"=")
    
    signature = hmac.new(
        SECRET_KEY.encode("utf-8"),
        f"{header_bytes.decode('utf-8')}.{payload_bytes.decode('utf-8')}".encode("utf-8"),
        hashlib.sha256
    ).digest()
    sig_bytes = base64.urlsafe_b64encode(signature).rstrip(b"=")
    
    return f"{header_bytes.decode('utf-8')}.{payload_bytes.decode('utf-8')}.{sig_bytes.decode('utf-8')}"


def decode_access_token(token: str) -> Optional[dict]:
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        header_b64, payload_b64, sig_b64 = parts
        
        # Verify signature
        expected_sig = hmac.new(
            SECRET_KEY.encode("utf-8"),
            f"{header_b64}.{payload_b64}".encode("utf-8"),
            hashlib.sha256
        ).digest()
        
        # Add padding back for b64decode
        rem = len(sig_b64) % 4
        if rem > 0:
            sig_b64 += "=" * (4 - rem)
        received_sig = base64.urlsafe_b64decode(sig_b64.encode("utf-8"))
        
        if not hmac.compare_digest(expected_sig, received_sig):
            return None
            
        rem = len(payload_b64) % 4
        if rem > 0:
            payload_b64 += "=" * (4 - rem)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64.encode("utf-8")).decode("utf-8"))
        
        if payload.get("exp") and payload["exp"] < time.time():
            return None
            
        return payload
    except Exception:
        return None


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db)
) -> Optional[User]:
    if not credentials:
        return None
    token = credentials.credentials
    payload = decode_access_token(token)
    if not payload or "sub" not in payload:
        return None
    username = payload["sub"]
    user = db.query(User).filter(User.username == username, User.is_active == True).first()
    return user


def require_user(current_user: Optional[User] = Depends(get_current_user)) -> User:
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="សូមចូលប្រើប្រាស់គណនីជាមុនសិន (Authentication required)",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return current_user


def require_role(roles: list[str]):
    def role_checker(current_user: User = Depends(require_user)) -> User:
        if current_user.role not in roles and current_user.role != "ADMIN":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="អ្នកមិនមានសិទ្ធិចូលដំណើរការមុខងារនេះទេ (Insufficient permissions)"
            )
        return current_user
    return role_checker
