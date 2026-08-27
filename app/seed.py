import datetime
from sqlalchemy.orm import Session
from app.database import engine, SessionLocal, Base
from app.models import Province, District, Commune, Village, User, Family, Member, SyncQueueLog
from app.auth import hash_password
from app.api.families import calculate_age


def init_db_and_seed(force: bool = False):
    Base.metadata.create_all(bind=engine)
    db: Session = SessionLocal()

    if force:
        # Clear existing data in reverse dependency order
        db.query(SyncQueueLog).delete()
        db.query(Member).delete()
        db.query(Family).delete()
        db.query(User).delete()
        db.query(Village).delete()
        db.query(Commune).delete()
        db.query(District).delete()
        db.query(Province).delete()
        db.commit()
    elif db.query(Province).first():
        print("Database already contains data, skipping seed.")
        db.close()
        return

    print("Seeding Cambodian geographic hierarchy (Prasat Trav Village, Kouk Doung, Angkor Chum, Siem Reap)...")

    # 1. Geographic Hierarchy: Prasat Trav Village in Kouk Doung Commune, Angkor Chum District, Siem Reap Province
    geo_data = [
        {
            "code": "17",
            "name_kh": "ខេត្តសៀមរាប",
            "name_en": "Siem Reap",
            "districts": [
                {
                    "code": "1701",
                    "name_kh": "ស្រុកអង្គរជុំ",
                    "name_en": "Angkor Chum",
                    "communes": [
                        {
                            "code": "170103",
                            "name_kh": "ឃុំគោកដូង",
                            "name_en": "Kouk Doung",
                            "villages": [
                                {
                                    "code": "17010307",
                                    "name_kh": "ភូមិប្រាសាទត្រាវ",
                                    "name_en": "Prasat Trav"
                                }
                            ]
                        }
                    ]
                }
            ]
        }
    ]

    village_map = {}
    for p_item in geo_data:
        prov = Province(code=p_item["code"], name_kh=p_item["name_kh"], name_en=p_item["name_en"])
        db.add(prov)
        db.flush()

        for d_item in p_item["districts"]:
            dist = District(province_id=prov.id, code=d_item["code"], name_kh=d_item["name_kh"], name_en=d_item["name_en"])
            db.add(dist)
            db.flush()

            for c_item in d_item["communes"]:
                comm = Commune(district_id=dist.id, code=c_item["code"], name_kh=c_item["name_kh"], name_en=c_item["name_en"])
                db.add(comm)
                db.flush()

                for v_item in c_item["villages"]:
                    vill = Village(commune_id=comm.id, code=v_item["code"], name_kh=v_item["name_kh"], name_en=v_item["name_en"])
                    db.add(vill)
                    db.flush()
                    village_map[v_item["code"]] = vill.id

    # 2. Users Seed Data (Admin, Reviewer, Collector)
    users = [
        User(
            username="admin",
            hashed_password=hash_password("admin123"),
            full_name="ឯកឧត្តម ប្រធានគ្រប់គ្រងប្រព័ន្ធ (Admin)",
            role="ADMIN",
            assigned_level="ALL",
            assigned_geo_code=None
        ),
        User(
            username="collector",
            hashed_password=hash_password("collector123"),
            full_name="កញ្ញា សុខ ស្រីម៉ៅ (អ្នកស្រង់ស្ថិតិ ភូមិប្រាសាទត្រាវ)",
            role="COLLECTOR",
            assigned_level="VILLAGE",
            assigned_geo_code="17010307"
        )
    ]

    for u in users:
        db.add(u)
    db.commit()

    collector_user = db.query(User).filter(User.username == "collector").first()
    target_village_id = village_map.get("17010307")

    # 3. Seed Sample Families & Members in ភូមិប្រាសាទត្រាវ
    sample_families = [
        {
            "village_id": target_village_id,
            "code": "FAM-17010307-0001",
            "poor": "GENERAL",
            "address": "ភូមិប្រាសាទត្រាវ ឃុំគោកដូង ស្រុកអង្គរជុំ ខេត្តសៀមរាប",
            "status": "APPROVED",
            "members": [
                {
                    "full_name": "សុខ ចាន់ដារ៉ា", "gender": "MALE", "nationality": "ខ្មែរ",
                    "dob": datetime.date(1982, 4, 15), "relation": "HEAD",
                    "edu": "HIGHER", "dropout": "ACTIVE", "grade": None,
                    "birth_cert": True, "occupation": "មន្ត្រីរាជការ", "disability": "គ្មាន",
                    "address": "ភូមិប្រាសាទត្រាវ ឃុំគោកដូង"
                },
                {
                    "full_name": "ឈុន ស្រីពេជ្រ", "gender": "FEMALE", "nationality": "ខ្មែរ",
                    "dob": datetime.date(1985, 8, 20), "relation": "SPOUSE",
                    "edu": "SECONDARY", "dropout": "ACTIVE", "grade": None,
                    "birth_cert": True, "occupation": "អាជីវករ", "disability": "គ្មាន",
                    "address": "ភូមិប្រាសាទត្រាវ ឃុំគោកដូង"
                },
                {
                    "full_name": "សុខ វាសនា", "gender": "MALE", "nationality": "ខ្មែរ",
                    "dob": datetime.date(2013, 2, 10), "relation": "CHILD",
                    "edu": "PRIMARY", "dropout": "ACTIVE", "grade": None,
                    "birth_cert": True, "occupation": "សិស្ស", "disability": "គ្មាន",
                    "address": "ភូមិប្រាសាទត្រាវ ឃុំគោកដូង"
                },
                {
                    "full_name": "សុខ ចរិយា", "gender": "FEMALE", "nationality": "ខ្មែរ",
                    "dob": datetime.date(2018, 9, 5), "relation": "CHILD",
                    "edu": "PRIMARY", "dropout": "ACTIVE", "grade": None,
                    "birth_cert": True, "occupation": "សិស្ស", "disability": "គ្មាន",
                    "address": "ភូមិប្រាសាទត្រាវ ឃុំគោកដូង"
                },
                {
                    "full_name": "សុខ មុនីរត្ន", "gender": "FEMALE", "nationality": "ខ្មែរ",
                    "dob": datetime.date(2026, 3, 1), "relation": "CHILD",
                    "edu": "NONE", "dropout": "ACTIVE", "grade": None,
                    "birth_cert": True, "occupation": "ទារក", "disability": "គ្មាន",
                    "address": "ភូមិប្រាសាទត្រាវ ឃុំគោកដូង"
                }
            ]
        },
        {
            "village_id": target_village_id,
            "code": "FAM-17010307-0002",
            "poor": "IDPOOR_1",
            "address": "ភូមិប្រាសាទត្រាវ ខាងកើតប្រាសាទ",
            "status": "APPROVED",
            "members": [
                {
                    "full_name": "គង់ សារ៉ាត់", "gender": "MALE", "nationality": "ខ្មែរ",
                    "dob": datetime.date(1978, 11, 12), "relation": "HEAD",
                    "edu": "NONE", "dropout": "ACTIVE", "grade": None,
                    "birth_cert": True, "occupation": "កសិករ", "disability": "គ្មាន",
                    "address": "ភូមិប្រាសាទត្រាវ"
                },
                {
                    "full_name": "ម៉ម ធីតា", "gender": "FEMALE", "nationality": "ខ្មែរ",
                    "dob": datetime.date(1980, 5, 2), "relation": "SPOUSE",
                    "edu": "PRIMARY", "dropout": "DROPOUT", "grade": "ថ្នាក់ទី ៤",
                    "birth_cert": True, "occupation": "កសិករ", "disability": "គ្មាន",
                    "address": "ភូមិប្រាសាទត្រាវ"
                },
                {
                    "full_name": "គង់ ពិសិដ្ឋ", "gender": "MALE", "nationality": "ខ្មែរ",
                    "dob": datetime.date(2011, 7, 18), "relation": "CHILD",
                    "edu": "PRIMARY", "dropout": "DROPOUT", "grade": "ថ្នាក់ទី ៦",
                    "birth_cert": False, "occupation": "ជួយការងារផ្ទះ", "disability": "គ្មាន",
                    "address": "ភូមិប្រាសាទត្រាវ"
                },
                {
                    "full_name": "គង់ គន្ធា", "gender": "FEMALE", "nationality": "ខ្មែរ",
                    "dob": datetime.date(2019, 12, 1), "relation": "CHILD",
                    "edu": "PRIMARY", "dropout": "ACTIVE", "grade": None,
                    "birth_cert": True, "occupation": "កុមារតូច", "disability": "គ្មាន",
                    "address": "ភូមិប្រាសាទត្រាវ"
                }
            ]
        },
        {
            "village_id": target_village_id,
            "code": "FAM-17010307-0003",
            "poor": "IDPOOR_2",
            "address": "ភូមិប្រាសាទត្រាវ ក្រុមទី ៣",
            "status": "PENDING_REVIEW",
            "members": [
                {
                    "full_name": "អ៊ុំ សំបូរ", "gender": "FEMALE", "nationality": "ខ្មែរ",
                    "dob": datetime.date(1965, 3, 14), "relation": "HEAD",
                    "edu": "NONE", "dropout": "ACTIVE", "grade": None,
                    "birth_cert": True, "occupation": "លក់ដូរតាមផ្ទះ", "disability": "ភ្នែកម្ខាងខ្សោយ",
                    "address": "ភូមិប្រាសាទត្រាវ"
                },
                {
                    "full_name": "សួស សុជាតិ", "gender": "MALE", "nationality": "ខ្មែរ",
                    "dob": datetime.date(2008, 10, 25), "relation": "CHILD",
                    "edu": "SECONDARY", "dropout": "DROPOUT", "grade": "ថ្នាក់ទី ៨",
                    "birth_cert": True, "occupation": "កម្មករសំណង់", "disability": "គ្មាន",
                    "address": "ភូមិប្រាសាទត្រាវ"
                }
            ]
        }
    ]

    for f_data in sample_families:
        fam = Family(
            village_id=f_data["village_id"],
            family_code=f_data["code"],
            poor_category=f_data["poor"],
            address_note=f_data["address"],
            status=f_data["status"],
            created_by_id=collector_user.id if collector_user else None
        )
        db.add(fam)
        db.flush()

        for m_data in f_data["members"]:
            age = calculate_age(m_data["dob"])
            m = Member(
                family_id=fam.id,
                full_name=m_data["full_name"],
                gender=m_data["gender"],
                nationality=m_data["nationality"],
                dob=m_data["dob"],
                age=age,
                relation=m_data["relation"],
                education_status=m_data["edu"],
                dropout_status=m_data["dropout"],
                dropout_grade=m_data["grade"],
                birth_cert=m_data["birth_cert"],
                disability=m_data["disability"],
                occupation=m_data["occupation"],
                current_address=m_data["address"]
            )
            db.add(m)

    db.commit()
    db.close()
    print("Seed completed successfully with Prasat Trav Village, Kouk Doung, Angkor Chum, Siem Reap!")


if __name__ == "__main__":
    init_db_and_seed(force=True)
