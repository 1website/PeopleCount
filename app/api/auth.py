from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User, UserAuditLog
from app.schemas import UserLogin, UserCreate, UserUpdate, UserOut, Token, UserAuditLogOut
from app.auth import verify_password, hash_password, create_access_token, require_user, require_role

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


@router.post("/login", response_model=Token)
def login(creds: UserLogin, request: Request, db: Session = Depends(get_db)):
    ip = request.client.host if request.client else "127.0.0.1"
    user_agent = request.headers.get("user-agent", "")[:250]

    user = db.query(User).filter(User.username == creds.username).first()
    if not user or not verify_password(creds.password, user.hashed_password):
        db.add(UserAuditLog(
            username=creds.username,
            full_name=user.full_name if user else None,
            role=user.role if user else None,
            action="LOGIN_FAILED",
            ip_address=ip,
            user_agent=user_agent
        ))
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="ឈ្មោះអ្នកប្រើ ឬពាក្យសម្ងាត់មិនត្រឹមត្រូវ (Invalid username or password)"
        )
    if not user.is_active:
        db.add(UserAuditLog(
            user_id=user.id,
            username=user.username,
            full_name=user.full_name,
            role=user.role,
            action="LOGIN_SUSPENDED",
            ip_address=ip,
            user_agent=user_agent
        ))
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="គណនីនេះត្រូវបានផ្អាកដំណើរការ (Account suspended)"
        )

    token = create_access_token({
        "sub": user.username,
        "role": user.role,
        "id": user.id,
        "name": user.full_name
    })

    db.add(UserAuditLog(
        user_id=user.id,
        username=user.username,
        full_name=user.full_name,
        role=user.role,
        action="LOGIN_SUCCESS",
        ip_address=ip,
        user_agent=user_agent
    ))
    db.commit()

    return {
        "access_token": token,
        "token_type": "bearer",
        "user_info": {
            "id": user.id,
            "username": user.username,
            "full_name": user.full_name,
            "role": user.role,
            "assigned_level": user.assigned_level,
            "assigned_geo_code": user.assigned_geo_code,
            "profile_picture": user.profile_picture
        }
    }


@router.get("/me")
def get_me(current_user: User = Depends(require_user)):
    return {
        "id": current_user.id,
        "username": current_user.username,
        "full_name": current_user.full_name,
        "role": current_user.role,
        "assigned_level": current_user.assigned_level,
        "assigned_geo_code": current_user.assigned_geo_code,
        "profile_picture": current_user.profile_picture
    }


@router.get("/users", response_model=list[UserOut])
def get_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["ADMIN"]))
):
    return db.query(User).order_by(User.id.asc()).all()


@router.post("/users", response_model=UserOut)
def create_user(
    data: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["ADMIN"]))
):
    existing = db.query(User).filter(User.username == data.username).first()
    if existing:
        raise HTTPException(status_code=400, detail="ឈ្មោះគណនីនេះមានរួចហើយ (Username already exists)")

    new_user = User(
        username=data.username,
        hashed_password=hash_password(data.password),
        full_name=data.full_name,
        role=data.role,
        assigned_level=data.assigned_level,
        assigned_geo_code=data.assigned_geo_code,
        profile_picture=data.profile_picture,
        is_active=True
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user


@router.put("/users/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    data: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["ADMIN"]))
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="រកមិនឃើញគណនីនេះទេ (User not found)")

    if data.full_name is not None:
        user.full_name = data.full_name
    if data.role is not None:
        user.role = data.role
    if data.assigned_level is not None:
        user.assigned_level = data.assigned_level
    if data.assigned_geo_code is not None:
        user.assigned_geo_code = data.assigned_geo_code
    if data.is_active is not None:
        user.is_active = data.is_active
    if data.profile_picture is not None:
        user.profile_picture = data.profile_picture if data.profile_picture != "__REMOVE__" else None
    if data.password:
        user.hashed_password = hash_password(data.password)

    db.commit()
    db.refresh(user)
    return user


@router.patch("/users/{user_id}/toggle-status", response_model=UserOut)
def toggle_user_status(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["ADMIN"]))
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="រកមិនឃើញគណនីនេះទេ (User not found)")
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="មិនអាចផ្អាកគណនីផ្ទាល់ខ្លួនបានទេ (Cannot suspend self)")

    user.is_active = not user.is_active
    db.commit()
    db.refresh(user)
    return user


@router.delete("/users/{user_id}")
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["ADMIN"]))
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="រកមិនឃើញគណនីនេះទេ (User not found)")
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="មិនអាចលុបគណនីផ្ទាល់ខ្លួនបានទេ (Cannot delete self)")

    db.delete(user)
    db.commit()
    return {"message": "បានលុបគណនីដោយជោគជ័យ (User deleted successfully)"}


@router.post("/logout")
def logout(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user)
):
    ip = request.client.host if request.client else "127.0.0.1"
    user_agent = request.headers.get("user-agent", "")[:250]
    db.add(UserAuditLog(
        user_id=current_user.id,
        username=current_user.username,
        full_name=current_user.full_name,
        role=current_user.role,
        action="LOGOUT",
        ip_address=ip,
        user_agent=user_agent
    ))
    db.commit()
    return {"message": "បានចាកចេញដោយជោគជ័យ (Logged out successfully)"}


@router.get("/logs", response_model=list[UserAuditLogOut])
def get_user_audit_logs(
    limit: int = 200,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["ADMIN"]))
):
    return db.query(UserAuditLog).order_by(UserAuditLog.created_at.desc()).limit(limit).all()

