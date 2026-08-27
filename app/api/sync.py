import datetime
from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Family, Member, Village, SyncQueueLog, User
from app.schemas import OfflineSyncPayload
from app.api.families import calculate_age, generate_family_code
from app.auth import get_current_user

router = APIRouter(prefix="/api/sync", tags=["Offline Data Sync"])


@router.post("/batch")
def sync_offline_batch(
    payload: OfflineSyncPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Receives batch of families collected while offline from mobile/tablet device.
    Dedupes using offline_client_id and assigns official codes.
    """
    synced_families = []
    total_members_synced = 0

    for fam_item in payload.families:
        # Check if already synced using offline_client_id
        if fam_item.offline_client_id:
            existing = db.query(Family).filter(Family.offline_client_id == fam_item.offline_client_id).first()
            if existing:
                synced_families.append({
                    "offline_client_id": fam_item.offline_client_id,
                    "family_code": existing.family_code,
                    "status": "ALREADY_SYNCED",
                    "id": existing.id
                })
                continue

        # Verify village exists
        village = db.query(Village).filter(Village.id == fam_item.village_id).first()
        if not village:
            continue

        family_code = generate_family_code(db, fam_item.village_id)
        status_val = "APPROVED" if (current_user and current_user.role in ["ADMIN", "REVIEWER"]) else "PENDING_REVIEW"

        new_family = Family(
            village_id=fam_item.village_id,
            family_code=family_code,
            poor_category=fam_item.poor_category,
            address_note=fam_item.address_note,
            status=status_val,
            created_by_id=current_user.id if current_user else None,
            offline_client_id=fam_item.offline_client_id
        )
        db.add(new_family)
        db.flush()

        for m_data in fam_item.members:
            age = calculate_age(m_data.dob)
            member = Member(
                family_id=new_family.id,
                full_name=m_data.full_name,
                gender=m_data.gender,
                nationality=m_data.nationality,
                dob=m_data.dob,
                age=age,
                relation=m_data.relation,
                education_status=m_data.education_status,
                dropout_status=m_data.dropout_status,
                dropout_grade=m_data.dropout_grade,
                birth_cert=m_data.birth_cert,
                disability=m_data.disability,
                occupation=m_data.occupation,
                current_address=m_data.current_address
            )
            db.add(member)
            total_members_synced += 1

        db.commit()
        db.refresh(new_family)

        synced_families.append({
            "offline_client_id": fam_item.offline_client_id,
            "family_code": new_family.family_code,
            "status": "SYNCED_OK",
            "id": new_family.id
        })

    # Log sync
    log = SyncQueueLog(
        client_id=payload.client_id,
        user_id=current_user.id if current_user else None,
        synced_families_count=len(synced_families),
        synced_members_count=total_members_synced,
        status="SUCCESS"
    )
    db.add(log)
    db.commit()

    return {
        "success": True,
        "message": f"បានធ្វើសមកាលកម្មដោយជោគជ័យ ចំនួនគ្រួសារ: {len(synced_families)}, សមាជិក: {total_members_synced}",
        "synced_count": len(synced_families),
        "synced_members_count": total_members_synced,
        "results": synced_families
    }


@router.get("/logs")
def get_sync_logs(db: Session = Depends(get_db)):
    logs = db.query(SyncQueueLog).order_by(SyncQueueLog.id.desc()).limit(50).all()
    return logs
