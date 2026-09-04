import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Family, Member, Village, Commune, District, Province, User
from app.schemas import (
    FamilyCreate, FamilyUpdate, FamilyOut, FamilyDetailOut,
    MemberCreate, MemberOut, MemberBase
)
from app.auth import require_user, require_role

router = APIRouter(prefix="/api/families", tags=["Families and Members"])


def calculate_age(dob: datetime.date) -> int:
    today = datetime.date.today()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


def generate_family_code(db: Session, village_id: int) -> str:
    village = db.query(Village).filter(Village.id == village_id).first()
    if not village:
        raise HTTPException(status_code=404, detail="រកមិនឃើញភូមិដែលបានបញ្ជាក់ (Village not found)")
    
    # Query all existing family codes for this village to avoid collision
    existing_codes = db.query(Family.family_code).filter(Family.village_id == village_id).all()
    max_num = 0
    prefix = f"FAM-{village.code}-"
    for (code,) in existing_codes:
        if code and code.startswith(prefix):
            suffix = code[len(prefix):]
            if suffix.isdigit():
                max_num = max(max_num, int(suffix))
    return f"{prefix}{max_num + 1:04d}"


def populate_family_metadata(f: Family) -> dict:
    head_member = next((m for m in f.members if m.relation == "HEAD"), None)
    head_name = head_member.full_name if head_member else (f.members[0].full_name if f.members else "គ្មានឈ្មោះ")
    
    vill = f.village
    comm = vill.commune if vill else None
    dist = comm.district if comm else None
    prov = dist.province if dist else None

    return {
        "id": f.id,
        "village_id": f.village_id,
        "family_code": f.family_code,
        "poor_category": f.poor_category,
        "address_note": f.address_note,
        "latitude": f.latitude,
        "longitude": f.longitude,
        "status": f.status,
        "created_at": f.created_at,
        "updated_at": f.updated_at,
        "members_count": len(f.members),
        "head_name": head_name,
        "village_name_kh": vill.name_kh if vill else None,
        "commune_name_kh": comm.name_kh if comm else None,
        "district_name_kh": dist.name_kh if dist else None,
        "province_name_kh": prov.name_kh if prov else None,
    }


@router.get("", response_model=List[FamilyOut])
def list_families(
    village_id: Optional[int] = None,
    commune_id: Optional[int] = None,
    poor_category: Optional[str] = None,
    status_filter: Optional[str] = None,
    search: Optional[str] = None,
    skip: int = 0,
    limit: int = 1000,
    db: Session = Depends(get_db)
):
    query = db.query(Family)
    
    if village_id:
        query = query.filter(Family.village_id == village_id)
    elif commune_id:
        village_ids = [v.id for v in db.query(Village.id).filter(Village.commune_id == commune_id).all()]
        query = query.filter(Family.village_id.in_(village_ids))
        
    if poor_category:
        query = query.filter(Family.poor_category == poor_category)
        
    if status_filter:
        query = query.filter(Family.status == status_filter)
        
    families = query.order_by(Family.id.desc()).offset(skip).limit(limit).all()
    
    result = []
    for f in families:
        meta = populate_family_metadata(f)
        if search:
            s_lower = search.lower()
            match_code = s_lower in f.family_code.lower()
            match_head = s_lower in (meta["head_name"] or "").lower()
            match_member = any(s_lower in m.full_name.lower() for m in f.members)
            if not (match_code or match_head or match_member):
                continue
        result.append(meta)
        
    return result


@router.post("", response_model=FamilyDetailOut)
def create_family(
    data: FamilyCreate,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(require_user)
):
    # Check offline duplicate if offline_client_id given
    if data.offline_client_id:
        existing = db.query(Family).filter(Family.offline_client_id == data.offline_client_id).first()
        if existing:
            return existing

    family_code = generate_family_code(db, data.village_id)
    
    # Default status: COLLECTOR creates PENDING_REVIEW or DRAFT, REVIEWER/ADMIN can create APPROVED
    status_val = "APPROVED"
    if current_user and current_user.role == "COLLECTOR":
        status_val = "PENDING_REVIEW"
        
    new_family = Family(
        village_id=data.village_id,
        family_code=family_code,
        poor_category=data.poor_category,
        address_note=data.address_note,
        latitude=data.latitude,
        longitude=data.longitude,
        status=status_val,
        created_by_id=current_user.id if current_user else None,
        offline_client_id=data.offline_client_id
    )
    db.add(new_family)
    db.flush()

    for m_data in data.members:
        calculated_age = calculate_age(m_data.dob)
        m_dropout_status = "NONE" if m_data.education_status == "NONE" else m_data.dropout_status
        m_dropout_grade = None if m_data.education_status == "NONE" else m_data.dropout_grade
        member = Member(
            family_id=new_family.id,
            full_name=m_data.full_name,
            gender=m_data.gender,
            nationality=m_data.nationality,
            dob=m_data.dob,
            age=calculated_age,
            relation=m_data.relation,
            education_status=m_data.education_status,
            dropout_status=m_dropout_status,
            dropout_grade=m_dropout_grade,
            birth_cert=m_data.birth_cert,
            disability=m_data.disability,
            occupation=m_data.occupation,
            current_address=m_data.current_address
        )
        db.add(member)

    db.commit()
    db.refresh(new_family)
    
    meta = populate_family_metadata(new_family)
    meta["members"] = new_family.members
    return meta


@router.get("/{family_id}", response_model=FamilyDetailOut)
def get_family(family_id: int, db: Session = Depends(get_db)):
    fam = db.query(Family).filter(Family.id == family_id).first()
    if not fam:
        raise HTTPException(status_code=404, detail="រកមិនឃើញព័ត៌មានគ្រួសារនេះទេ (Family not found)")
    meta = populate_family_metadata(fam)
    meta["members"] = fam.members
    return meta


@router.put("/{family_id}")
def update_family(
    family_id: int,
    data: FamilyUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user)
):
    fam = db.query(Family).filter(Family.id == family_id).first()
    if not fam:
        raise HTTPException(status_code=404, detail="រកមិនឃើញព័ត៌មានគ្រួសារនេះទេ (Family not found)")
        
    if data.poor_category is not None:
        fam.poor_category = data.poor_category
    if data.address_note is not None:
        fam.address_note = data.address_note
    if data.latitude is not None:
        fam.latitude = data.latitude
    if data.longitude is not None:
        fam.longitude = data.longitude
    if data.village_id is not None:
        fam.village_id = data.village_id
    if current_user.role == "ADMIN" and data.status is not None:
        fam.status = data.status
        
    db.commit()
    db.refresh(fam)
    return {"message": "បានកែប្រែដោយជោគជ័យ (Updated successfully)"}


@router.patch("/{family_id}/status")
def change_family_status(
    family_id: int,
    new_status: str = Query(..., pattern="^(APPROVED|PENDING_REVIEW|REJECTED)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["ADMIN"]))
):
    fam = db.query(Family).filter(Family.id == family_id).first()
    if not fam:
        raise HTTPException(status_code=404, detail="រកមិនឃើញព័ត៌មានគ្រួសារនេះទេ (Family not found)")
        
    fam.status = new_status
    db.commit()
    return {"message": f"បានផ្លាស់ប្តូរស្ថានភាពទៅជា {new_status}", "status": new_status}


@router.delete("/{family_id}")
def delete_family(
    family_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["ADMIN"]))
):
    fam = db.query(Family).filter(Family.id == family_id).first()
    if not fam:
        raise HTTPException(status_code=404, detail="រកមិនឃើញគ្រួសារនេះទេ (Family not found)")
    db.delete(fam)
    db.commit()
    return {"message": "បានលុបព័ត៌មានគ្រួសារដោយជោគជ័យ (Family deleted)"}


# --- Member Endpoints ---
@router.post("/{family_id}/members", response_model=MemberOut)
def add_member(
    family_id: int,
    data: MemberCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user)
):
    fam = db.query(Family).filter(Family.id == family_id).first()
    if not fam:
        raise HTTPException(status_code=404, detail="រកមិនឃើញគ្រួសារ (Family not found)")
        
    calculated_age = calculate_age(data.dob)
    m_dropout_status = "NONE" if data.education_status == "NONE" else data.dropout_status
    m_dropout_grade = None if data.education_status == "NONE" else data.dropout_grade
    new_member = Member(
        family_id=family_id,
        full_name=data.full_name,
        gender=data.gender,
        nationality=data.nationality,
        dob=data.dob,
        age=calculated_age,
        relation=data.relation,
        education_status=data.education_status,
        dropout_status=m_dropout_status,
        dropout_grade=m_dropout_grade,
        birth_cert=data.birth_cert,
        disability=data.disability,
        occupation=data.occupation,
        current_address=data.current_address
    )
    db.add(new_member)
    db.commit()
    db.refresh(new_member)
    return new_member


@router.put("/members/{member_id}", response_model=MemberOut)
def update_member(
    member_id: int,
    data: MemberCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user)
):
    member = db.query(Member).filter(Member.id == member_id).first()
    if not member:
        raise HTTPException(status_code=404, detail="រកមិនឃើញសមាជិក (Member not found)")
        
    calculated_age = calculate_age(data.dob)
    member.full_name = data.full_name
    member.gender = data.gender
    member.nationality = data.nationality
    member.dob = data.dob
    member.age = calculated_age
    member.relation = data.relation
    member.education_status = data.education_status
    member.dropout_status = "NONE" if data.education_status == "NONE" else data.dropout_status
    member.dropout_grade = None if data.education_status == "NONE" else data.dropout_grade
    member.birth_cert = data.birth_cert
    member.disability = data.disability
    member.occupation = data.occupation
    member.current_address = data.current_address
    
    db.commit()
    db.refresh(member)
    return member


@router.delete("/members/{member_id}")
def delete_member(
    member_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user)
):
    member = db.query(Member).filter(Member.id == member_id).first()
    if not member:
        raise HTTPException(status_code=404, detail="រកមិនឃើញសមាជិក (Member not found)")
    db.delete(member)
    db.commit()
    return {"message": "បានលុបសមាជិកដោយជោគជ័យ (Member deleted)"}
