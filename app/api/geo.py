from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Province, District, Commune, Village, User
from app.schemas import (
    ProvinceOut, ProvinceCreate,
    DistrictOut, DistrictCreate,
    CommuneOut, CommuneCreate,
    VillageOut, VillageCreate
)
from app.auth import require_user, require_role

router = APIRouter(prefix="/api/geo", tags=["Geographic Hierarchy"])


# --- Auto-Code Helpers ---
def generate_province_code(db: Session) -> str:
    provinces = db.query(Province.code).all()
    codes = [int(p[0]) for p in provinces if p[0].isdigit()]
    next_num = max(codes, default=0) + 1
    return f"{next_num:02d}"


def generate_district_code(db: Session, province_id: int) -> str:
    prov = db.query(Province).filter(Province.id == province_id).first()
    if not prov:
        raise HTTPException(status_code=404, detail="រកមិនឃើញខេត្ត (Province not found)")
    districts = db.query(District.code).filter(District.province_id == province_id).all()
    prov_prefix = prov.code
    suffixes = [
        int(d[0][len(prov_prefix):]) for d in districts
        if d[0].startswith(prov_prefix) and d[0][len(prov_prefix):].isdigit()
    ]
    next_num = max(suffixes, default=0) + 1
    return f"{prov_prefix}{next_num:02d}"


def generate_commune_code(db: Session, district_id: int) -> str:
    dist = db.query(District).filter(District.id == district_id).first()
    if not dist:
        raise HTTPException(status_code=404, detail="រកមិនឃើញស្រុក/ខណ្ឌ (District not found)")
    communes = db.query(Commune.code).filter(Commune.district_id == district_id).all()
    dist_prefix = dist.code
    suffixes = [
        int(c[0][len(dist_prefix):]) for c in communes
        if c[0].startswith(dist_prefix) and c[0][len(dist_prefix):].isdigit()
    ]
    next_num = max(suffixes, default=0) + 1
    return f"{dist_prefix}{next_num:02d}"


def generate_village_code(db: Session, commune_id: int) -> str:
    comm = db.query(Commune).filter(Commune.id == commune_id).first()
    if not comm:
        raise HTTPException(status_code=404, detail="រកមិនឃើញឃុំ/សង្កាត់ (Commune not found)")
    villages = db.query(Village.code).filter(Village.commune_id == commune_id).all()
    comm_prefix = comm.code
    suffixes = [
        int(v[0][len(comm_prefix):]) for v in villages
        if v[0].startswith(comm_prefix) and v[0][len(comm_prefix):].isdigit()
    ]
    next_num = max(suffixes, default=0) + 1
    return f"{comm_prefix}{next_num:02d}"


# --- Read Endpoints ---
@router.get("/provinces", response_model=List[ProvinceOut])
def get_provinces(db: Session = Depends(get_db)):
    return db.query(Province).order_by(Province.code).all()


@router.get("/districts", response_model=List[DistrictOut])
def get_districts(province_id: Optional[int] = None, db: Session = Depends(get_db)):
    query = db.query(District)
    if province_id:
        query = query.filter(District.province_id == province_id)
    return query.order_by(District.code).all()


@router.get("/communes", response_model=List[CommuneOut])
def get_communes(district_id: Optional[int] = None, db: Session = Depends(get_db)):
    query = db.query(Commune)
    if district_id:
        query = query.filter(Commune.district_id == district_id)
    return query.order_by(Commune.code).all()


@router.get("/villages", response_model=List[VillageOut])
def get_villages(commune_id: Optional[int] = None, db: Session = Depends(get_db)):
    query = db.query(Village)
    if commune_id:
        query = query.filter(Village.commune_id == commune_id)
    return query.order_by(Village.code).all()


@router.get("/full-hierarchy")
def get_full_hierarchy(db: Session = Depends(get_db)):
    """Returns complete nested tree for geographic selection & offline caching"""
    provinces = db.query(Province).order_by(Province.code).all()
    result = []
    for prov in provinces:
        p_data = {
            "id": prov.id,
            "code": prov.code,
            "name_kh": prov.name_kh,
            "name_en": prov.name_en,
            "districts": []
        }
        for dist in prov.districts:
            d_data = {
                "id": dist.id,
                "code": dist.code,
                "name_kh": dist.name_kh,
                "name_en": dist.name_en,
                "communes": []
            }
            for comm in dist.communes:
                c_data = {
                    "id": comm.id,
                    "code": comm.code,
                    "name_kh": comm.name_kh,
                    "name_en": comm.name_en,
                    "villages": [
                        {
                            "id": v.id,
                            "code": v.code,
                            "name_kh": v.name_kh,
                            "name_en": v.name_en
                        }
                        for v in comm.villages
                    ]
                }
                d_data["communes"].append(c_data)
            p_data["districts"].append(d_data)
        result.append(p_data)
    return result


# --- Create Endpoints with Auto-code Generation ---
@router.post("/provinces", response_model=ProvinceOut)
def create_province(
    data: ProvinceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["ADMIN"]))
):
    code = data.code or generate_province_code(db)
    prov = Province(code=code, name_kh=data.name_kh, name_en=data.name_en)
    db.add(prov)
    db.commit()
    db.refresh(prov)
    return prov


@router.post("/districts", response_model=DistrictOut)
def create_district(
    data: DistrictCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["ADMIN"]))
):
    code = data.code or generate_district_code(db, data.province_id)
    dist = District(
        province_id=data.province_id,
        code=code,
        name_kh=data.name_kh,
        name_en=data.name_en
    )
    db.add(dist)
    db.commit()
    db.refresh(dist)
    return dist


@router.post("/communes", response_model=CommuneOut)
def create_commune(
    data: CommuneCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["ADMIN"]))
):
    code = data.code or generate_commune_code(db, data.district_id)
    comm = Commune(
        district_id=data.district_id,
        code=code,
        name_kh=data.name_kh,
        name_en=data.name_en
    )
    db.add(comm)
    db.commit()
    db.refresh(comm)
    return comm


@router.post("/villages", response_model=VillageOut)
def create_village(
    data: VillageCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["ADMIN", "REVIEWER"]))
):
    code = data.code or generate_village_code(db, data.commune_id)
    vill = Village(
        commune_id=data.commune_id,
        code=code,
        name_kh=data.name_kh,
        name_en=data.name_en
    )
    db.add(vill)
    db.commit()
    db.refresh(vill)
    return vill
