from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.database import get_db
from app.models import Family, Member, Village, Commune, District, Province, User
from app.auth import require_user

router = APIRouter(prefix="/api/gis", tags=["GIS & Technology"])


@router.get("/map-data")
def get_gis_map_data(
    village_id: Optional[int] = None,
    poor_category: Optional[str] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user)
) -> Dict[str, Any]:
    """
    Retrieve GIS mapping data for families, poverty hotspots, and geographic distribution.
    Supports filtering by village, poverty category, and search query.
    """
    query = db.query(Family)

    # Apply role-based geographic access control
    if current_user.role != "ADMIN" and current_user.assigned_level != "ALL" and current_user.assigned_geo_code:
        lvl = current_user.assigned_level
        code = current_user.assigned_geo_code
        if lvl == "PROVINCE":
            query = query.join(Family.village).join(Village.commune).join(Commune.district).join(District.province).filter(Province.code == code)
        elif lvl == "DISTRICT":
            query = query.join(Family.village).join(Village.commune).join(Commune.district).filter(District.code == code)
        elif lvl == "COMMUNE":
            query = query.join(Family.village).join(Village.commune).filter(Commune.code == code)
        elif lvl == "VILLAGE":
            query = query.join(Family.village).filter(Village.code == code)

    # Optional Filters
    if village_id:
        query = query.filter(Family.village_id == village_id)

    if poor_category and poor_category in ["IDPOOR_1", "IDPOOR_2", "GENERAL"]:
        query = query.filter(Family.poor_category == poor_category)

    if search:
        search_term = f"%{search.strip()}%"
        # Filter families where family_code, address_note, or member name matches
        matching_family_ids = db.query(Member.family_id).filter(Member.full_name.ilike(search_term))
        query = query.filter(
            or_(
                Family.family_code.ilike(search_term),
                Family.address_note.ilike(search_term),
                Family.id.in_(matching_family_ids)
            )
        )

    families = query.all()

    # Villages list for filtering and map centering
    villages_query = db.query(Village)
    villages = villages_query.all()
    villages_data = []
    for v in villages:
        villages_data.append({
            "id": v.id,
            "code": v.code,
            "name_kh": v.name_kh,
            "latitude": v.latitude or 13.5852,
            "longitude": v.longitude or 103.7125,
            "commune_name_kh": v.commune.name_kh if v.commune else None,
            "district_name_kh": v.commune.district.name_kh if v.commune and v.commune.district else None,
            "province_name_kh": v.commune.district.province.name_kh if v.commune and v.commune.district and v.commune.district.province else None,
        })

    # Summary metrics
    idpoor_1_count = 0
    idpoor_2_count = 0
    general_count = 0
    total_population = 0
    total_children = 0
    total_elders = 0
    total_dropouts = 0

    households = []
    default_center_lat = 13.5852
    default_center_lng = 103.7125

    for f in families:
        # Poverty count
        if f.poor_category == "IDPOOR_1":
            idpoor_1_count += 1
        elif f.poor_category == "IDPOOR_2":
            idpoor_2_count += 1
        else:
            general_count += 1

        # Members analytics
        members = f.members or []
        m_count = len(members)
        total_population += m_count

        children = [m for m in members if m.age < 18]
        elders = [m for m in members if m.age >= 60]
        dropouts = [m for m in members if m.dropout_status == "DROPOUT"]

        total_children += len(children)
        total_elders += len(elders)
        total_dropouts += len(dropouts)

        # Head of family
        head_m = next((m for m in members if m.relation == "HEAD"), None)
        head_name = head_m.full_name if head_m else (members[0].full_name if members else "មិនបញ្ជាក់")

        # Resolve GPS coordinates with fallback
        lat = f.latitude
        lng = f.longitude
        if lat is None or lng is None:
            # Fallback based on village or deterministic spread
            v_lat = f.village.latitude if f.village and f.village.latitude else default_center_lat
            v_lng = f.village.longitude if f.village and f.village.longitude else default_center_lng
            lat = v_lat + (((f.id * 7) % 13) - 6) * 0.0009
            lng = v_lng + (((f.id * 5) % 11) - 5) * 0.0011

        households.append({
            "id": f.id,
            "family_code": f.family_code,
            "poor_category": f.poor_category,
            "address_note": f.address_note or "គ្មាន",
            "status": f.status,
            "latitude": round(lat, 6),
            "longitude": round(lng, 6),
            "head_name": head_name,
            "members_count": m_count,
            "children_count": len(children),
            "elders_count": len(elders),
            "dropouts_count": len(dropouts),
            "village_id": f.village_id,
            "village_name_kh": f.village.name_kh if f.village else "-",
            "commune_name_kh": f.village.commune.name_kh if f.village and f.village.commune else "-",
            "district_name_kh": f.village.commune.district.name_kh if f.village and f.village.commune and f.village.commune.district else "-"
        })

    # Determine center
    center_lat = default_center_lat
    center_lng = default_center_lng
    if households:
        center_lat = sum(h["latitude"] for h in households) / len(households)
        center_lng = sum(h["longitude"] for h in households) / len(households)

    return {
        "center": {
            "latitude": round(center_lat, 6),
            "longitude": round(center_lng, 6),
            "zoom": 15 if village_id else 14
        },
        "summary": {
            "total_households": len(households),
            "idpoor_1_count": idpoor_1_count,
            "idpoor_2_count": idpoor_2_count,
            "general_count": general_count,
            "total_population": total_population,
            "total_children": total_children,
            "total_elders": total_elders,
            "total_dropouts": total_dropouts
        },
        "villages": villages_data,
        "households": households
    }
