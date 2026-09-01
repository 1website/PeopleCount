import json
import datetime
from typing import Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.database import get_db, engine
from app.models import (
    Province, District, Commune, Village,
    User, Family, Member, SyncQueueLog, UserAuditLog,
    now_cambodia
)
from app.auth import require_role

router = APIRouter(prefix="/api/backup", tags=["Database Backup & Restore"])


def serialize_model(instance) -> Dict[str, Any]:
    """Helper to convert a SQLAlchemy model instance into a clean JSON-serializable dictionary."""
    data = {}
    for column in instance.__table__.columns:
        val = getattr(instance, column.name)
        if isinstance(val, (datetime.date, datetime.datetime)):
            data[column.name] = val.isoformat()
        else:
            data[column.name] = val
    return data


@router.get("/stats")
def get_backup_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["ADMIN"]))
):
    """Return live record counts across all tables and current database engine."""
    dialect_name = db.bind.dialect.name
    engine_label = "PostgreSQL (Neon Cloud)" if dialect_name == "postgresql" else "SQLite (Local/Temp)"
    
    return {
        "engine": engine_label,
        "dialect": dialect_name,
        "counts": {
            "provinces": db.query(Province).count(),
            "districts": db.query(District).count(),
            "communes": db.query(Commune).count(),
            "villages": db.query(Village).count(),
            "users": db.query(User).count(),
            "families": db.query(Family).count(),
            "members": db.query(Member).count(),
            "sync_queue_logs": db.query(SyncQueueLog).count(),
            "user_audit_logs": db.query(UserAuditLog).count()
        },
        "total_records": (
            db.query(Province).count() +
            db.query(District).count() +
            db.query(Commune).count() +
            db.query(Village).count() +
            db.query(User).count() +
            db.query(Family).count() +
            db.query(Member).count()
        ),
        "timestamp": now_cambodia().isoformat()
    }


@router.get("/export")
def export_database_backup(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["ADMIN"]))
):
    """
    Export entire database snapshot as a structured, versioned, database-agnostic JSON archive.
    Can be restored across both SQLite and PostgreSQL.
    """
    timestamp = now_cambodia()
    time_str = timestamp.strftime("%Y-%m-%d_%H%M%S")
    filename = f"census_backup_{time_str}.json"

    # Query all tables in logical order
    provinces = [serialize_model(p) for p in db.query(Province).order_by(Province.id).all()]
    districts = [serialize_model(d) for d in db.query(District).order_by(District.id).all()]
    communes = [serialize_model(c) for c in db.query(Commune).order_by(Commune.id).all()]
    villages = [serialize_model(v) for v in db.query(Village).order_by(Village.id).all()]
    users = [serialize_model(u) for u in db.query(User).order_by(User.id).all()]
    families = [serialize_model(f) for f in db.query(Family).order_by(Family.id).all()]
    members = [serialize_model(m) for m in db.query(Member).order_by(Member.id).all()]
    sync_logs = [serialize_model(s) for s in db.query(SyncQueueLog).order_by(SyncQueueLog.id).all()]
    audit_logs = [serialize_model(a) for a in db.query(UserAuditLog).order_by(UserAuditLog.id).all()]

    backup_payload = {
        "system": "Cambodia Demographic, Family Census & Education Tracking System",
        "version": "1.0.0",
        "exported_at": timestamp.isoformat(),
        "exported_by": current_user.username,
        "database_dialect": db.bind.dialect.name,
        "summary": {
            "provinces": len(provinces),
            "districts": len(districts),
            "communes": len(communes),
            "villages": len(villages),
            "users": len(users),
            "families": len(families),
            "members": len(members),
            "sync_queue_logs": len(sync_logs),
            "user_audit_logs": len(audit_logs)
        },
        "data": {
            "provinces": provinces,
            "districts": districts,
            "communes": communes,
            "villages": villages,
            "users": users,
            "families": families,
            "members": members,
            "sync_queue_logs": sync_logs,
            "user_audit_logs": audit_logs
        }
    }

    json_content = json.dumps(backup_payload, ensure_ascii=False, indent=2)

    return Response(
        content=json_content,
        media_type="application/json",
        headers={
            "Content-Disposition": f"attachment; filename={filename}",
            "Cache-Control": "no-cache"
        }
    )


@router.post("/restore")
async def restore_database_backup(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["ADMIN"]))
):
    """
    Restore database snapshot from an uploaded JSON backup file.
    Executes in a single atomic transaction: all or nothing rollback on any error.
    Synchronizes primary key sequences on PostgreSQL.
    """
    if not file.filename.endswith(".json"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ឯកសារត្រូវតែជាទម្រង់ .json (File must be a valid .json backup file)"
        )

    try:
        content = await file.read()
        payload = json.loads(content.decode("utf-8"))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"ឯកសារ JSON មិនត្រឹមត្រូវ (Invalid JSON format): {str(e)}"
        )

    # Validate essential structure
    if "system" not in payload or "data" not in payload:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ទម្រង់ឯកសារ Backup មិនត្រូវស្តង់ដារប្រព័ន្ធ (Unrecognized backup archive structure)"
        )

    data = payload["data"]
    is_sqlite = db.bind.dialect.name == "sqlite"

    try:
        # 1. Clear existing data in reverse dependency order to prevent foreign key errors
        db.query(UserAuditLog).delete()
        db.query(SyncQueueLog).delete()
        db.query(Member).delete()
        db.query(Family).delete()
        db.query(Village).delete()
        db.query(Commune).delete()
        db.query(District).delete()
        db.query(Province).delete()
        db.query(User).delete()

        # 2. Insert Provinces
        for p in data.get("provinces", []):
            db.add(Province(
                id=p["id"],
                code=p["code"],
                name_kh=p["name_kh"],
                name_en=p["name_en"]
            ))
        db.flush()

        # 3. Insert Districts
        for d in data.get("districts", []):
            db.add(District(
                id=d["id"],
                province_id=d["province_id"],
                code=d["code"],
                name_kh=d["name_kh"],
                name_en=d["name_en"]
            ))
        db.flush()

        # 4. Insert Communes
        for c in data.get("communes", []):
            db.add(Commune(
                id=c["id"],
                district_id=c["district_id"],
                code=c["code"],
                name_kh=c["name_kh"],
                name_en=c["name_en"]
            ))
        db.flush()

        # 5. Insert Villages
        for v in data.get("villages", []):
            db.add(Village(
                id=v["id"],
                commune_id=v["commune_id"],
                code=v["code"],
                name_kh=v["name_kh"],
                name_en=v["name_en"]
            ))
        db.flush()

        # 6. Insert Users
        for u in data.get("users", []):
            created_at = datetime.datetime.fromisoformat(u["created_at"]) if u.get("created_at") else now_cambodia()
            db.add(User(
                id=u["id"],
                username=u["username"],
                hashed_password=u["hashed_password"],
                full_name=u["full_name"],
                role=u["role"],
                assigned_level=u.get("assigned_level", "ALL"),
                assigned_geo_code=u.get("assigned_geo_code"),
                profile_picture=u.get("profile_picture"),
                is_active=u.get("is_active", True),
                created_at=created_at
            ))
        db.flush()

        # 7. Insert Families
        for f in data.get("families", []):
            c_at = datetime.datetime.fromisoformat(f["created_at"]) if f.get("created_at") else now_cambodia()
            u_at = datetime.datetime.fromisoformat(f["updated_at"]) if f.get("updated_at") else now_cambodia()
            db.add(Family(
                id=f["id"],
                village_id=f["village_id"],
                family_code=f["family_code"],
                poor_category=f.get("poor_category", "GENERAL"),
                address_note=f.get("address_note"),
                status=f.get("status", "APPROVED"),
                created_by_id=f.get("created_by_id"),
                offline_client_id=f.get("offline_client_id"),
                created_at=c_at,
                updated_at=u_at
            ))
        db.flush()

        # 8. Insert Members
        for m in data.get("members", []):
            dob = datetime.date.fromisoformat(m["dob"]) if isinstance(m["dob"], str) else m["dob"]
            c_at = datetime.datetime.fromisoformat(m["created_at"]) if m.get("created_at") else now_cambodia()
            db.add(Member(
                id=m["id"],
                family_id=m["family_id"],
                full_name=m["full_name"],
                gender=m["gender"],
                nationality=m.get("nationality", "ខ្មែរ"),
                dob=dob,
                age=m["age"],
                relation=m.get("relation", "CHILD"),
                education_status=m.get("education_status", "PRIMARY"),
                dropout_status=m.get("dropout_status", "ACTIVE"),
                dropout_grade=m.get("dropout_grade"),
                birth_cert=m.get("birth_cert", "0"),
                disability=m.get("disability"),
                occupation=m.get("occupation"),
                current_address=m.get("current_address"),
                created_at=c_at
            ))
        db.flush()

        # 9. Insert Sync Logs
        for s in data.get("sync_queue_logs", []):
            c_at = datetime.datetime.fromisoformat(s["created_at"]) if s.get("created_at") else now_cambodia()
            db.add(SyncQueueLog(
                id=s["id"],
                client_id=s["client_id"],
                user_id=s.get("user_id"),
                synced_families_count=s.get("synced_families_count", 0),
                synced_members_count=s.get("synced_members_count", 0),
                status=s.get("status", "SUCCESS"),
                created_at=c_at
            ))
        db.flush()

        # 10. Insert Audit Logs
        for a in data.get("user_audit_logs", []):
            c_at = datetime.datetime.fromisoformat(a["created_at"]) if a.get("created_at") else now_cambodia()
            db.add(UserAuditLog(
                id=a["id"],
                user_id=a.get("user_id"),
                username=a["username"],
                full_name=a.get("full_name"),
                role=a.get("role"),
                action=a.get("action", "RESTORE_DATABASE"),
                ip_address=a.get("ip_address"),
                user_agent=a.get("user_agent"),
                created_at=c_at
            ))
        db.flush()

        # 11. Sync PostgreSQL primary key sequences so subsequent auto-increment inserts don't collide
        if not is_sqlite:
            tables = [
                "provinces", "districts", "communes", "villages",
                "users", "families", "members", "sync_queue_logs", "user_audit_logs"
            ]
            for table in tables:
                try:
                    db.execute(text(
                        f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                        f"COALESCE((SELECT MAX(id) FROM {table}), 1), true);"
                    ))
                except Exception:
                    pass

        # Commit atomic transaction
        db.commit()

        # Add audit log for restore action
        try:
            audit = UserAuditLog(
                user_id=current_user.id,
                username=current_user.username,
                full_name=current_user.full_name,
                role=current_user.role,
                action="DATABASE_RESTORE_COMPLETED",
                ip_address="Vercel/Cloud",
                user_agent="Admin Console"
            )
            db.add(audit)
            db.commit()
        except Exception:
            pass

        return {
            "success": True,
            "message": "ការស្តារទិន្នន័យបានជោគជ័យ ១០០% (Database restored successfully)",
            "restored_summary": {
                "provinces": len(data.get("provinces", [])),
                "districts": len(data.get("districts", [])),
                "communes": len(data.get("communes", [])),
                "villages": len(data.get("villages", [])),
                "users": len(data.get("users", [])),
                "families": len(data.get("families", [])),
                "members": len(data.get("members", []))
            }
        }

    except Exception as err:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"បរាជ័យក្នុងការស្តារទិន្នន័យ (Failed to restore database): {str(err)}"
        )
