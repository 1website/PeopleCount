import datetime
from sqlalchemy.orm import Session
from app.database import engine, SessionLocal, Base
from app.models import Province, District, Commune, Village, User, Family, Member, SyncQueueLog
from app.auth import hash_password
from app.api.families import calculate_age


def init_db_and_seed(force: bool = False):
    Base.metadata.create_all(bind=engine)

    # Automatic Schema Migration for newly added columns with dialect-specific syntax
    try:
        from sqlalchemy import text
        is_pg = engine.dialect.name == "postgresql"
        migrations = [
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS profile_picture TEXT" if is_pg else "ALTER TABLE users ADD COLUMN profile_picture TEXT",
            "ALTER TABLE families ADD COLUMN IF NOT EXISTS offline_client_id VARCHAR(100)" if is_pg else "ALTER TABLE families ADD COLUMN offline_client_id VARCHAR(100)",
            "ALTER TABLE members ADD COLUMN IF NOT EXISTS is_studying BOOLEAN DEFAULT TRUE" if is_pg else "ALTER TABLE members ADD COLUMN is_studying BOOLEAN DEFAULT 1",
            "ALTER TABLE members ADD COLUMN IF NOT EXISTS dropout_grade VARCHAR(20)" if is_pg else "ALTER TABLE members ADD COLUMN dropout_grade VARCHAR(20)",
            "ALTER TABLE families ADD COLUMN IF NOT EXISTS latitude FLOAT" if is_pg else "ALTER TABLE families ADD COLUMN latitude FLOAT",
            "ALTER TABLE families ADD COLUMN IF NOT EXISTS longitude FLOAT" if is_pg else "ALTER TABLE families ADD COLUMN longitude FLOAT",
            "ALTER TABLE villages ADD COLUMN IF NOT EXISTS latitude FLOAT" if is_pg else "ALTER TABLE villages ADD COLUMN latitude FLOAT",
            "ALTER TABLE villages ADD COLUMN IF NOT EXISTS longitude FLOAT" if is_pg else "ALTER TABLE villages ADD COLUMN longitude FLOAT",
            "UPDATE members SET dropout_status = 'NONE', dropout_grade = NULL WHERE education_status = 'NONE' AND (dropout_status != 'NONE' OR dropout_grade IS NOT NULL)",
            "UPDATE villages SET latitude = 13.5852, longitude = 103.7125 WHERE code = '17010307' AND latitude IS NULL",
            """
            UPDATE families 
            SET latitude = 13.5852 + (((id * 7) % 13) - 6) * 0.0009,
                longitude = 103.7125 + (((id * 5) % 11) - 5) * 0.0011
            WHERE latitude IS NULL OR longitude IS NULL
            """,
            "UPDATE users SET assigned_geo_code = '17010307' WHERE username = 'collector' AND (assigned_geo_code IS NULL OR assigned_geo_code = '17010312')"
        ]
        for sql in migrations:
            try:
                with engine.connect() as conn:
                    conn.execute(text(sql))
                    conn.commit()
            except Exception:
                pass
    except Exception as e:
        print(f"Migration error: {e}")

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

    village_map = {}

    # 1. Geographic Hierarchy
    if not db.query(Province).first():
        print("Seeding Cambodian geographic hierarchy (Prasat Trav Village, Kouk Doung, Angkor Chum, Siem Reap)...")
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
                        vill_lat = 13.5852 if v_item["code"] == "17010307" else None
                        vill_lng = 103.7125 if v_item["code"] == "17010307" else None
                        vill = Village(
                            commune_id=comm.id,
                            code=v_item["code"],
                            name_kh=v_item["name_kh"],
                            name_en=v_item["name_en"],
                            latitude=vill_lat,
                            longitude=vill_lng
                        )
                        db.add(vill)
                        db.flush()
                        village_map[v_item["code"]] = vill.id
        db.commit()
    else:
        for v in db.query(Village).all():
            village_map[v.code] = v.id

    # 2. Users Seed Data (Admin, Reviewer, Collector)
    if not db.query(User).filter(User.username == "admin").first():
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
    if not target_village_id:
        first_v = db.query(Village).first()
        target_village_id = first_v.id if first_v else 1

    # 3. Seed Sample Families & Members if database has fewer than 10 families
    if db.query(Family).count() < 10:
        import os
        import json
        json_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "sample_census_51.json")
        if os.path.exists(json_path):
            try:
                with open(json_path, "r", encoding="utf-8") as fp:
                    full_fams = json.load(fp)
                for f_data in full_fams:
                    if db.query(Family).filter(Family.family_code == f_data["family_code"]).first():
                        continue
                    fam = Family(
                        village_id=target_village_id,
                        family_code=f_data["family_code"],
                        poor_category=f_data["poor_category"],
                        address_note=f_data["address_note"],
                        latitude=f_data.get("latitude"),
                        longitude=f_data.get("longitude"),
                        status=f_data.get("status", "APPROVED"),
                        created_by_id=collector_user.id if collector_user else None
                    )
                    db.add(fam)
                    db.flush()
                    for m_data in f_data["members"]:
                        dob_val = datetime.date.fromisoformat(m_data["dob"]) if isinstance(m_data["dob"], str) else m_data["dob"]
                        age = calculate_age(dob_val)
                        m = Member(
                            family_id=fam.id,
                            full_name=m_data["full_name"],
                            gender=m_data["gender"],
                            nationality=m_data.get("nationality", "ខ្មែរ"),
                            dob=dob_val,
                            age=age,
                            relation=m_data["relation"],
                            education_status=m_data["education_status"],
                            dropout_status=m_data["dropout_status"],
                            dropout_grade=m_data.get("dropout_grade"),
                            birth_cert=str(m_data.get("birth_cert", "0")),
                            disability=m_data.get("disability", "គ្មាន"),
                            occupation=m_data.get("occupation", ""),
                            current_address=m_data.get("current_address", "")
                        )
                        db.add(m)
                db.commit()
                print(f"[Seed] Successfully seeded {len(full_fams)} families from sample_census_51.json")
            except Exception as e:
                print(f"[Seed] Error seeding from JSON: {e}")

    if db.query(Family).count() > 0:
        print("Database already contains families, skipping fallback seed.")
        db.close()
        return

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
                    "edu": "NONE", "dropout": "NONE", "grade": None,
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
                    "edu": "NONE", "dropout": "NONE", "grade": None,
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
                    "edu": "NONE", "dropout": "NONE", "grade": None,
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
            latitude=f_data.get("lat", 13.5852 + (len(sample_families) - 2) * 0.0012),
            longitude=f_data.get("lng", 103.7125 + (len(sample_families) - 2) * 0.0015),
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
