import datetime
from sqlalchemy import (
    Column, Integer, String, Boolean, Date, DateTime, ForeignKey, Text, Enum
)
from sqlalchemy.orm import relationship
from app.database import Base

# Cambodia Timezone (ICT: Indochina Time, UTC+7)
CAMBODIA_TZ = datetime.timezone(datetime.timedelta(hours=7))


def now_cambodia():
    """Return current timestamp in Cambodia timezone (UTC+7 / ICT)"""
    return datetime.datetime.now(CAMBODIA_TZ).replace(tzinfo=None)


class Province(Base):
    __tablename__ = "provinces"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(2), unique=True, index=True, nullable=False)  # e.g., '12'
    name_kh = Column(String(100), nullable=False)
    name_en = Column(String(100), nullable=False)

    districts = relationship("District", back_populates="province", cascade="all, delete-orphan")


class District(Base):
    __tablename__ = "districts"

    id = Column(Integer, primary_key=True, index=True)
    province_id = Column(Integer, ForeignKey("provinces.id", ondelete="CASCADE"), nullable=False)
    code = Column(String(4), unique=True, index=True, nullable=False)  # e.g., '1201'
    name_kh = Column(String(100), nullable=False)
    name_en = Column(String(100), nullable=False)

    province = relationship("Province", back_populates="districts")
    communes = relationship("Commune", back_populates="district", cascade="all, delete-orphan")


class Commune(Base):
    __tablename__ = "communes"

    id = Column(Integer, primary_key=True, index=True)
    district_id = Column(Integer, ForeignKey("districts.id", ondelete="CASCADE"), nullable=False)
    code = Column(String(6), unique=True, index=True, nullable=False)  # e.g., '120101'
    name_kh = Column(String(100), nullable=False)
    name_en = Column(String(100), nullable=False)

    district = relationship("District", back_populates="communes")
    villages = relationship("Village", back_populates="commune", cascade="all, delete-orphan")


class Village(Base):
    __tablename__ = "villages"

    id = Column(Integer, primary_key=True, index=True)
    commune_id = Column(Integer, ForeignKey("communes.id", ondelete="CASCADE"), nullable=False)
    code = Column(String(8), unique=True, index=True, nullable=False)  # e.g., '12010101'
    name_kh = Column(String(100), nullable=False)
    name_en = Column(String(100), nullable=False)

    commune = relationship("Commune", back_populates="villages")
    families = relationship("Family", back_populates="village", cascade="all, delete-orphan")


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    hashed_password = Column(String(200), nullable=False)
    full_name = Column(String(100), nullable=False)
    # Roles: 'ADMIN', 'REVIEWER', 'COLLECTOR'
    role = Column(String(20), default="COLLECTOR", nullable=False)
    # Assigned geographic level: 'ALL', 'PROVINCE', 'DISTRICT', 'COMMUNE', 'VILLAGE'
    assigned_level = Column(String(20), default="ALL")
    # Geographic code of assigned jurisdiction (e.g., '12010101' for specific village)
    assigned_geo_code = Column(String(20), nullable=True)
    profile_picture = Column(Text, nullable=True)  # Base64 image data URI or URL
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=now_cambodia)

    families_created = relationship("Family", back_populates="creator")


class Family(Base):
    __tablename__ = "families"

    id = Column(Integer, primary_key=True, index=True)
    village_id = Column(Integer, ForeignKey("villages.id", ondelete="CASCADE"), nullable=False)
    family_code = Column(String(30), unique=True, index=True, nullable=False)  # e.g., 'FAM-12010101-0001'
    # Poverty category: 'IDPOOR_1' (ក្រ១), 'IDPOOR_2' (ក្រ២), 'GENERAL' (ទូទៅ)
    poor_category = Column(String(20), default="GENERAL", nullable=False)
    address_note = Column(String(255), nullable=True)
    # Status: 'DRAFT', 'SUBMITTED', 'APPROVED'
    status = Column(String(20), default="APPROVED", nullable=False)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    offline_client_id = Column(String(100), nullable=True)  # UUID for offline sync tracking
    created_at = Column(DateTime, default=now_cambodia)
    updated_at = Column(DateTime, default=now_cambodia, onupdate=now_cambodia)

    village = relationship("Village", back_populates="families")
    creator = relationship("User", back_populates="families_created")
    members = relationship("Member", back_populates="family", cascade="all, delete-orphan")


class Member(Base):
    __tablename__ = "members"

    id = Column(Integer, primary_key=True, index=True)
    family_id = Column(Integer, ForeignKey("families.id", ondelete="CASCADE"), nullable=False)
    full_name = Column(String(120), nullable=False)  # គោត្តនាម-នាម
    gender = Column(String(10), nullable=False)  # 'MALE' (ប្រុស), 'FEMALE' (ស្រី)
    nationality = Column(String(50), default="ខ្មែរ", nullable=False)  # សញ្ជាតិ
    dob = Column(Date, nullable=False)  # ថ្ងៃខែឆ្នាំកំណើត
    age = Column(Integer, nullable=False)  # គណនាស្វ័យប្រវត្តិតាម DOB
    # Relation to head of family:
    # 'HEAD' (មេគ្រួសារ), 'SPOUSE' (ប្រពន្ធ/ប្តី), 'CHILD' (កូន), 'PARENT' (ឪពុក/ម្តាយ), 'RELATIVE' (សាច់ញាតិ), 'OTHER' (ផ្សេងៗ)
    relation = Column(String(30), default="CHILD", nullable=False)
    
    # Education & School Status:
    # 'NONE' (មិនបានរៀន), 'PRIMARY' (ចូលរៀនបឋម), 'SECONDARY' (ចូលរៀនមធ្យម), 'HIGHER' (ឧត្តមសិក្សា)
    education_status = Column(String(30), default="PRIMARY", nullable=False)
    # Dropout status: 'ACTIVE' (កំពុងរៀន), 'DROPOUT' (បោះបង់ការសិក្សា), 'SUSPENDED' (បង្អង់ការសិក្សា), 'COMPLETED' (បានបញ្ចប់), 'NONE' (មិនបានរៀន)
    dropout_status = Column(String(30), default="ACTIVE", nullable=False)
    dropout_grade = Column(String(50), nullable=True)  # កម្រិតថ្នាក់ដែលបោះបង់ e.g. ថ្នាក់ទី ៧
    
    # Administrative Documents & Remarks:
    birth_cert = Column(String(50), default="0", nullable=True)  # សំបុត្រកំណើត (លេខឡាតាំងប៉ុណ្ណោះ e.g. '0', '1234', default: '0')
    disability = Column(String(100), nullable=True)  # ពិការភាព (គ្មាន ឬបញ្ជាក់ប្រភេទ)
    occupation = Column(String(100), nullable=True)  # មុខរបរ
    current_address = Column(String(255), nullable=True)  # ទីកន្លែងស្នាក់នៅបច្ចុប្បន្ន
    
    created_at = Column(DateTime, default=now_cambodia)

    family = relationship("Family", back_populates="members")


class SyncQueueLog(Base):
    __tablename__ = "sync_queue_logs"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(String(100), nullable=False)
    user_id = Column(Integer, nullable=True)
    synced_families_count = Column(Integer, default=0)
    synced_members_count = Column(Integer, default=0)
    status = Column(String(20), default="SUCCESS")
    created_at = Column(DateTime, default=now_cambodia)


class UserAuditLog(Base):
    __tablename__ = "user_audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    username = Column(String(50), nullable=False)
    full_name = Column(String(100), nullable=True)
    role = Column(String(20), nullable=True)
    action = Column(String(50), default="LOGIN_SUCCESS")  # LOGIN_SUCCESS, LOGIN_FAILED, LOGIN_SUSPENDED, LOGOUT
    ip_address = Column(String(50), nullable=True)
    user_agent = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=now_cambodia, index=True)
