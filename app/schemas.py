import re
from typing import List, Optional
from datetime import date, datetime
from pydantic import BaseModel, Field, field_validator


# --- User & Auth Schemas ---
class Token(BaseModel):
    access_token: str
    token_type: str
    user_info: dict


class UserLogin(BaseModel):
    username: str
    password: str


class UserCreate(BaseModel):
    username: str
    password: str
    full_name: str
    role: str = "COLLECTOR"  # ADMIN, REVIEWER, COLLECTOR
    assigned_level: str = "ALL"  # ALL, PROVINCE, DISTRICT, COMMUNE, VILLAGE
    assigned_geo_code: Optional[str] = None
    profile_picture: Optional[str] = None


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    role: Optional[str] = None
    assigned_level: Optional[str] = None
    assigned_geo_code: Optional[str] = None
    password: Optional[str] = None
    is_active: Optional[bool] = None
    profile_picture: Optional[str] = None



class UserOut(BaseModel):
    id: int
    username: str
    full_name: str
    role: str
    assigned_level: str
    assigned_geo_code: Optional[str]
    profile_picture: Optional[str] = None
    is_active: bool

    class Config:
        from_attributes = True


# --- Geographic Hierarchy Schemas ---
class VillageBase(BaseModel):
    name_kh: str
    name_en: str


class VillageCreate(VillageBase):
    commune_id: int
    code: Optional[str] = None  # Auto-generated if not provided


class VillageOut(VillageBase):
    id: int
    commune_id: int
    code: str

    class Config:
        from_attributes = True


class CommuneBase(BaseModel):
    name_kh: str
    name_en: str


class CommuneCreate(CommuneBase):
    district_id: int
    code: Optional[str] = None


class CommuneOut(CommuneBase):
    id: int
    district_id: int
    code: str
    villages: List[VillageOut] = []

    class Config:
        from_attributes = True


class DistrictBase(BaseModel):
    name_kh: str
    name_en: str


class DistrictCreate(DistrictBase):
    province_id: int
    code: Optional[str] = None


class DistrictOut(DistrictBase):
    id: int
    province_id: int
    code: str
    communes: List[CommuneOut] = []

    class Config:
        from_attributes = True


class ProvinceBase(BaseModel):
    name_kh: str
    name_en: str


class ProvinceCreate(ProvinceBase):
    code: Optional[str] = None


class ProvinceOut(ProvinceBase):
    id: int
    code: str
    districts: List[DistrictOut] = []

    class Config:
        from_attributes = True


# --- Member Schemas ---
class MemberBase(BaseModel):
    full_name: str
    gender: str  # MALE, FEMALE
    nationality: str = "ខ្មែរ"
    dob: date
    relation: str = "CHILD"  # HEAD, SPOUSE, CHILD, PARENT, RELATIVE, OTHER
    education_status: str = "PRIMARY"  # NONE, PRIMARY, SECONDARY, HIGHER
    dropout_status: str = "ACTIVE"  # ACTIVE, DROPOUT, SUSPENDED, COMPLETED
    dropout_grade: Optional[str] = None
    birth_cert: str = "0"
    disability: Optional[str] = None
    occupation: Optional[str] = None
    current_address: Optional[str] = None

    @field_validator("birth_cert", mode="before")
    @classmethod
    def validate_birth_cert(cls, v):
        if v is None or v is False:
            return "0"
        if v is True:
            return "1"
        s = str(v).strip()
        khmer_to_latin = {
            '០': '0', '១': '1', '២': '2', '៣': '3', '៤': '4',
            '៥': '5', '៦': '6', '៧': '7', '៨': '8', '៩': '9'
        }
        for kh, lat in khmer_to_latin.items():
            s = s.replace(kh, lat)
        digits = re.sub(r"[^0-9]", "", s)
        return digits if digits else "0"

    @field_validator("dropout_grade", mode="before")
    @classmethod
    def validate_dropout_grade(cls, v):
        if v is None:
            return None
        s = str(v).strip()
        if not s:
            return None
        khmer_to_latin = {
            '០': '0', '១': '1', '២': '2', '៣': '3', '៤': '4',
            '៥': '5', '៦': '6', '៧': '7', '៨': '8', '៩': '9'
        }
        for kh, lat in khmer_to_latin.items():
            s = s.replace(kh, lat)
        return s.strip() or None


class MemberCreate(MemberBase):
    pass


class MemberOut(MemberBase):
    id: int
    family_id: int
    age: int
    created_at: datetime

    class Config:
        from_attributes = True


# --- Family Schemas ---
class FamilyBase(BaseModel):
    village_id: int
    poor_category: str = "GENERAL"  # IDPOOR_1, IDPOOR_2, GENERAL
    address_note: Optional[str] = None
    status: str = "APPROVED"  # DRAFT, PENDING_REVIEW, APPROVED


class FamilyCreate(FamilyBase):
    members: List[MemberCreate] = []
    offline_client_id: Optional[str] = None


class FamilyUpdate(BaseModel):
    poor_category: Optional[str] = None
    address_note: Optional[str] = None
    village_id: Optional[int] = None
    status: Optional[str] = None


class FamilyOut(FamilyBase):
    id: int
    family_code: str
    created_at: datetime
    updated_at: Optional[datetime]
    members_count: Optional[int] = 0
    head_name: Optional[str] = None
    village_name_kh: Optional[str] = None
    commune_name_kh: Optional[str] = None
    district_name_kh: Optional[str] = None
    province_name_kh: Optional[str] = None

    class Config:
        from_attributes = True


class FamilyDetailOut(FamilyOut):
    members: List[MemberOut] = []


# --- Offline Sync Schemas ---
class OfflineSyncPayload(BaseModel):
    client_id: str
    families: List[FamilyCreate]


# --- User Audit Log Schemas ---
class UserAuditLogOut(BaseModel):
    id: int
    user_id: Optional[int] = None
    username: str
    full_name: Optional[str] = None
    role: Optional[str] = None
    action: str
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True
