import datetime
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_login_and_roles():
    # Admin login
    res = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert res.status_code == 200, f"Admin login failed: {res.text}"
    token_data = res.json()
    assert "access_token" in token_data
    assert token_data["user_info"]["role"] == "ADMIN"

    # Collector login
    res = client.post("/api/auth/login", json={"username": "collector", "password": "collector123"})
    assert res.status_code == 200
    assert res.json()["user_info"]["role"] == "COLLECTOR"
    print("[OK] Auth and RBAC test passed")


def test_geographic_hierarchy():
    res = client.get("/api/geo/provinces")
    assert res.status_code == 200
    provinces = res.json()
    assert len(provinces) >= 1
    siem_reap = next(p for p in provinces if p["code"] == "17")
    assert siem_reap["name_kh"] == "ខេត្តសៀមរាប"

    # Check districts in Siem Reap
    res_dist = client.get(f"/api/geo/districts?province_id={siem_reap['id']}")
    assert res_dist.status_code == 200
    districts = res_dist.json()
    assert len(districts) >= 1
    angkor_chum = next(d for d in districts if d["code"] == "1701")
    assert angkor_chum["name_kh"] == "ស្រុកអង្គរជុំ"

    # Check communes
    res_comm = client.get(f"/api/geo/communes?district_id={angkor_chum['id']}")
    assert res_comm.status_code == 200
    communes = res_comm.json()
    kouk_doung = next(c for c in communes if c["code"] == "170103")
    assert kouk_doung["name_kh"] == "ឃុំគោកដូង"

    # Check village
    res_vill = client.get(f"/api/geo/villages?commune_id={kouk_doung['id']}")
    assert res_vill.status_code == 200
    villages = res_vill.json()
    assert villages[0]["code"] == "17010307"
    assert villages[0]["name_kh"] == "ភូមិប្រាសាទត្រាវ"
    print("[OK] Geographic hierarchy cascading lookup passed (Siem Reap -> Angkor Chum -> Kouk Doung -> Phum Prasat Trav)")


def test_family_and_member_registration():
    # Login as admin to obtain token
    auth_res = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    headers = {"Authorization": f"Bearer {auth_res.json()['access_token']}"}

    # Get a village
    vill_res = client.get("/api/geo/villages")
    v_id = vill_res.json()[0]["id"]

    # Register a new family with 2 members
    family_payload = {
        "village_id": v_id,
        "poor_category": "IDPOOR_2",
        "address_note": "Test house 88",
        "status": "APPROVED",
        "members": [
            {
                "full_name": "Heng Rothana",
                "gender": "MALE",
                "nationality": "Khmer",
                "dob": "1988-03-15",
                "relation": "HEAD",
                "education_status": "SECONDARY",
                "dropout_status": "ACTIVE",
                "dropout_grade": None,
                "birth_cert": True,
                "disability": "None",
                "occupation": "Technician",
                "current_address": "Phnom Penh"
            },
            {
                "full_name": "Heng Vicheka",
                "gender": "FEMALE",
                "nationality": "Khmer",
                "dob": "2015-05-10",
                "relation": "CHILD",
                "education_status": "PRIMARY",
                "dropout_status": "DROPOUT",
                "dropout_grade": "Grade 3",
                "birth_cert": True,
                "disability": "None",
                "occupation": "Student",
                "current_address": "Phnom Penh"
            }
        ]
    }

    create_res = client.post("/api/families", json=family_payload, headers=headers)
    assert create_res.status_code == 200, f"Failed to create family: {create_res.text}"
    created_fam = create_res.json()
    assert created_fam["family_code"].startswith("FAM-")
    assert len(created_fam["members"]) == 2

    # Verify auto-calculated age
    head = next(m for m in created_fam["members"] if m["relation"] == "HEAD")
    child = next(m for m in created_fam["members"] if m["relation"] == "CHILD")
    assert head["age"] >= 35
    # Verify adding a new member to an existing family
    new_m_payload = {
        "full_name": "Sok Vibol Extra",
        "gender": "MALE",
        "nationality": "Khmer",
        "dob": "2020-01-15",
        "relation": "CHILD",
        "education_status": "PRIMARY",
        "dropout_status": "ACTIVE",
        "dropout_grade": "ថ្នាក់ទី ២",
        "birth_cert": "54321",
        "disability": "None",
        "occupation": "Student",
        "current_address": ""
    }
    add_m_res = client.post(f"/api/families/{created_fam['id']}/members", json=new_m_payload, headers=headers)
    assert add_m_res.status_code == 200
    added_m = add_m_res.json()
    assert added_m["full_name"] == "Sok Vibol Extra"
    assert added_m["birth_cert"] == "54321"
    assert added_m["dropout_grade"] == "ថ្នាក់ទី 2"
    assert added_m["age"] >= 6

    # Verify adding a member with COMPLETED study status and Khmer digits in birth_cert
    completed_m_payload = {
        "full_name": "Sok Somaly Graduate",
        "gender": "FEMALE",
        "nationality": "Khmer",
        "dob": "2000-05-20",
        "relation": "CHILD",
        "education_status": "HIGHER",
        "dropout_status": "COMPLETED",
        "dropout_grade": "បរិញ្ញាបត្រ",
        "birth_cert": "៩៨៧៦៥",
        "disability": "None",
        "occupation": "Engineer",
        "current_address": "Siem Reap"
    }
    comp_res = client.post(f"/api/families/{created_fam['id']}/members", json=completed_m_payload, headers=headers)
    assert comp_res.status_code == 200
    comp_m = comp_res.json()
    assert comp_m["dropout_status"] == "COMPLETED"
    assert comp_m["dropout_grade"] == "បរិញ្ញាបត្រ"
    assert comp_m["birth_cert"] == "98765"  # Khmer digits '៩៨៧៦៥' successfully normalized to '98765'

    # Verify deleting the added members from the family
    client.delete(f"/api/families/members/{comp_m['id']}", headers=headers)
    del_m_res = client.delete(f"/api/families/members/{added_m['id']}", headers=headers)
    assert del_m_res.status_code == 200

    # Verify member is gone
    fam_after = client.get(f"/api/families/{created_fam['id']}").json()
    assert not any(m["id"] == added_m["id"] for m in fam_after["members"])
    assert not any(m["id"] == comp_m["id"] for m in fam_after["members"])

    print(f"[OK] Family registration, dynamic member addition & deletion passed")


def test_reporting_and_excel():
    stats_res = client.get("/api/reports/dashboard-stats")
    assert stats_res.status_code == 200
    stats = stats_res.json()
    assert stats["demographics"]["total_population"] > 0
    assert stats["demographics"]["male"] > 0
    assert stats["demographics"]["female"] > 0
    assert "birth_certificate" in stats
    assert "education" in stats
    assert "infants_0" in stats["education"]
    assert stats["education"]["infants_0"] >= 1
    assert "dropout_groups" in stats["education"]
    assert "grades_0_6" in stats["education"]["dropout_groups"]
    assert "grades_7_9" in stats["education"]["dropout_groups"]
    assert "grades_10_12" in stats["education"]["dropout_groups"]
    print(f"[OK] Reporting stats test passed (Pop: {stats['demographics']['total_population']}, Infants (Age 0): {stats['education']['infants_0']}, Dropouts: {stats['education']['dropouts_count']})")

    # Test Excel Export (All, and with filters)
    excel_res = client.get("/api/reports/export/excel")
    assert excel_res.status_code == 200
    assert excel_res.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert len(excel_res.content) > 1000  # valid binary excel

    # Test Excel Export with province and district filters
    prov_res = client.get("/api/geo/provinces").json()
    if prov_res:
        p_id = prov_res[0]["id"]
        excel_prov = client.get(f"/api/reports/export/excel?province_id={p_id}")
        assert excel_prov.status_code == 200
        assert len(excel_prov.content) > 1000

    print("[OK] Excel Export test passed (with hierarchy filtering)")


def test_offline_sync():
    vill_res = client.get("/api/geo/villages")
    v_id = vill_res.json()[0]["id"]

    sync_payload = {
        "client_id": "tablet-device-test-uuid-999",
        "families": [
            {
                "village_id": v_id,
                "poor_category": "GENERAL",
                "address_note": "Offline note",
                "status": "PENDING_REVIEW",
                "offline_client_id": "offline-item-001-uuid",
                "members": [
                    {
                        "full_name": "Chan Sophea",
                        "gender": "MALE",
                        "nationality": "Khmer",
                        "dob": "1995-01-01",
                        "relation": "HEAD",
                        "education_status": "SECONDARY",
                        "dropout_status": "ACTIVE",
                        "dropout_grade": None,
                        "birth_cert": True,
                        "disability": "None",
                        "occupation": "Driver",
                        "current_address": "Phnom Penh"
                    }
                ]
            }
        ]
    }

    res = client.post("/api/sync/batch", json=sync_payload)
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["synced_count"] == 1
    print("[OK] Offline batch sync test passed")


def test_user_management_crud():
    # 1. Login as Admin
    login_res = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert login_res.status_code == 200
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Get Users List
    users_res = client.get("/api/auth/users", headers=headers)
    assert users_res.status_code == 200
    users = users_res.json()
    assert len(users) >= 2

    # 3. Create User
    new_user_payload = {
        "full_name": "Test Collector Person",
        "username": f"test_collector_{int(datetime.datetime.now().timestamp())}",
        "password": "password123",
        "role": "COLLECTOR",
        "assigned_level": "VILLAGE",
        "assigned_geo_code": "17010301"
    }
    create_res = client.post("/api/auth/users", json=new_user_payload, headers=headers)
    assert create_res.status_code == 200
    created_u = create_res.json()
    user_id = created_u["id"]
    assert created_u["full_name"] == new_user_payload["full_name"]
    assert created_u["is_active"] is True

    # 4. Update User
    update_payload = {
        "full_name": "Updated Collector Name",
        "role": "ADMIN"
    }
    update_res = client.put(f"/api/auth/users/{user_id}", json=update_payload, headers=headers)
    assert update_res.status_code == 200
    updated_u = update_res.json()
    assert updated_u["full_name"] == "Updated Collector Name"
    assert updated_u["role"] == "ADMIN"

    # 5. Toggle Status (Disable then re-enable)
    toggle_res = client.patch(f"/api/auth/users/{user_id}/toggle-status", headers=headers)
    assert toggle_res.status_code == 200
    assert toggle_res.json()["is_active"] is False

    toggle_res2 = client.patch(f"/api/auth/users/{user_id}/toggle-status", headers=headers)
    assert toggle_res2.status_code == 200
    assert toggle_res2.json()["is_active"] is True

    # 6. Delete User
    del_res = client.delete(f"/api/auth/users/{user_id}", headers=headers)
    assert del_res.status_code == 200
    print("[OK] User management CRUD (Create, Read, Update, Toggle Status, Delete) test passed")


def test_user_audit_logs():
    # 1. Admin login generates LOGIN_SUCCESS
    admin_login = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert admin_login.status_code == 200
    admin_token = admin_login.json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # 2. Failed login generates LOGIN_FAILED
    failed_login = client.post("/api/auth/login", json={"username": "baduser", "password": "wrongpassword"})
    assert failed_login.status_code == 401

    # 3. Collector login generates LOGIN_SUCCESS
    coll_login = client.post("/api/auth/login", json={"username": "collector", "password": "collector123"})
    assert coll_login.status_code == 200
    coll_token = coll_login.json()["access_token"]
    coll_headers = {"Authorization": f"Bearer {coll_token}"}

    # 4. Collector attempts to access audit logs -> 403 Forbidden
    coll_logs_res = client.get("/api/auth/logs", headers=coll_headers)
    assert coll_logs_res.status_code == 403, f"Non-admin should get 403, got {coll_logs_res.status_code}"

    # 5. Collector logout generates LOGOUT
    coll_logout = client.post("/api/auth/logout", headers=coll_headers)
    assert coll_logout.status_code == 200

    # 6. Admin accesses audit logs -> 200 OK with logged actions
    logs_res = client.get("/api/auth/logs", headers=admin_headers)
    assert logs_res.status_code == 200
    logs = logs_res.json()
    assert len(logs) >= 3
    actions = [log["action"] for log in logs]
    assert "LOGIN_SUCCESS" in actions
    assert "LOGIN_FAILED" in actions
    assert "LOGOUT" in actions
    print("[OK] User access audit logs (login, failed login, logout, RBAC protection) test passed")


def test_backup_and_restore():
    # 1. Collector login -> try to export backup -> 403 Forbidden
    coll_auth = client.post("/api/auth/login", json={"username": "collector", "password": "collector123"})
    coll_headers = {"Authorization": f"Bearer {coll_auth.json()['access_token']}"}
    coll_export = client.get("/api/backup/export", headers=coll_headers)
    assert coll_export.status_code == 403, f"Collector should be forbidden from export, got {coll_export.status_code}"

    # 2. Admin login -> get stats
    admin_auth = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    admin_headers = {"Authorization": f"Bearer {admin_auth.json()['access_token']}"}

    stats_res = client.get("/api/backup/stats", headers=admin_headers)
    assert stats_res.status_code == 200
    stats = stats_res.json()
    assert "counts" in stats
    assert stats["counts"]["provinces"] >= 1
    assert stats["counts"]["families"] >= 1

    # 3. Admin exports full backup
    export_res = client.get("/api/backup/export", headers=admin_headers)
    assert export_res.status_code == 200
    assert "attachment; filename=" in export_res.headers.get("Content-Disposition", "")
    backup_data = export_res.json()
    assert backup_data["system"] == "Cambodia Demographic, Family Census & Education Tracking System"
    assert "data" in backup_data
    assert len(backup_data["data"]["provinces"]) >= 1
    assert len(backup_data["data"]["families"]) >= 1

    # 4. Admin restores from backup payload
    import io
    import json
    backup_bytes = json.dumps(backup_data).encode("utf-8")
    files = {"file": ("test_backup.json", io.BytesIO(backup_bytes), "application/json")}
    restore_res = client.post("/api/backup/restore", headers=admin_headers, files=files)
    assert restore_res.status_code == 200, f"Restore failed: {restore_res.text}"
    restore_data = restore_res.json()
    assert restore_data["success"] is True

    # 5. Verify database records are intact after restore
    after_stats_res = client.get("/api/backup/stats", headers=admin_headers)
    assert after_stats_res.status_code == 200
    after_stats = after_stats_res.json()
    assert after_stats["counts"]["provinces"] == stats["counts"]["provinces"]
    assert after_stats["counts"]["families"] == stats["counts"]["families"]

    # 6. Test invalid file format rejection
    bad_files = {"file": ("invalid.txt", io.BytesIO(b"not json"), "text/plain")}
    bad_res = client.post("/api/backup/restore", headers=admin_headers, files=bad_files)
    assert bad_res.status_code == 400

    print("[OK] Database backup and restore test passed")


def test_collector_permissions_and_family_management():
    # 1. Login as collector
    res = client.post("/api/auth/login", json={"username": "collector", "password": "collector123"})
    assert res.status_code == 200
    collector_headers = {"Authorization": f"Bearer {res.json()['access_token']}"}

    # 2. Collector creates a family (status should default to PENDING_REVIEW)
    vill_res = client.get("/api/geo/villages")
    v_id = vill_res.json()[0]["id"]
    create_payload = {
        "village_id": v_id,
        "poor_category": "GENERAL",
        "address_note": "Original address",
        "members": [
            {
                "full_name": "Test Collector Family Head",
                "gender": "MALE",
                "nationality": "Khmer",
                "dob": "1990-01-01",
                "relation": "HEAD",
                "education_status": "PRIMARY",
                "dropout_status": "ACTIVE",
                "birth_cert": "0"
            }
        ]
    }
    create_res = client.post("/api/families", json=create_payload, headers=collector_headers)
    assert create_res.status_code == 200
    fam = create_res.json()
    fam_id = fam["id"]
    assert fam["status"] == "PENDING_REVIEW"

    # 3. Collector can list families and view details
    list_res = client.get("/api/families", headers=collector_headers)
    assert list_res.status_code == 200
    assert any(f["id"] == fam_id for f in list_res.json())

    detail_res = client.get(f"/api/families/{fam_id}", headers=collector_headers)
    assert detail_res.status_code == 200
    assert detail_res.json()["family_code"] == fam["family_code"]

    # 4. Collector can edit family info (poor_category and address_note)
    update_res = client.put(
        f"/api/families/{fam_id}",
        json={"poor_category": "IDPOOR_1", "address_note": "Collector updated address", "status": "APPROVED"},
        headers=collector_headers
    )
    assert update_res.status_code == 200
    # Verify poor_category changed, but status remained PENDING_REVIEW (Collector cannot approve via PUT)
    fam_check = client.get(f"/api/families/{fam_id}").json()
    assert fam_check["poor_category"] == "IDPOOR_1"
    assert fam_check["address_note"] == "Collector updated address"
    assert fam_check["status"] == "PENDING_REVIEW"

    # 5. Collector CANNOT approve family via status endpoint (Forbidden)
    approve_attempt = client.patch(
        f"/api/families/{fam_id}/status?new_status=APPROVED",
        headers=collector_headers
    )
    assert approve_attempt.status_code == 403, "Collector must NOT be allowed to approve families"

    # 6. Collector can add a member and edit a member
    add_m_res = client.post(
        f"/api/families/{fam_id}/members",
        json={
            "full_name": "Collector Added Member",
            "gender": "FEMALE",
            "nationality": "Khmer",
            "dob": "2018-06-15",
            "relation": "CHILD",
            "education_status": "PRIMARY",
            "dropout_status": "ACTIVE",
            "birth_cert": "123"
        },
        headers=collector_headers
    )
    assert add_m_res.status_code == 200
    new_m = add_m_res.json()
    assert new_m["full_name"] == "Collector Added Member"

    # Collector edits member
    edit_m_res = client.put(
        f"/api/families/members/{new_m['id']}",
        json={
            "full_name": "Collector Edited Member Name",
            "gender": "FEMALE",
            "nationality": "Khmer",
            "dob": "2018-06-15",
            "relation": "CHILD",
            "education_status": "PRIMARY",
            "dropout_status": "DROPOUT",
            "dropout_grade": "ថ្នាក់ទី ៣",
            "birth_cert": "999"
        },
        headers=collector_headers
    )
    assert edit_m_res.status_code == 200
    assert edit_m_res.json()["full_name"] == "Collector Edited Member Name"
    assert edit_m_res.json()["dropout_status"] == "DROPOUT"
    assert edit_m_res.json()["dropout_grade"] == "ថ្នាក់ទី 3"
    assert edit_m_res.json()["birth_cert"] == "999"

    # 7. Collector CANNOT delete family (Forbidden)
    delete_attempt = client.delete(f"/api/families/{fam_id}", headers=collector_headers)
    assert delete_attempt.status_code == 403, "Collector must NOT be allowed to delete families"

    # 8. Clean up as Admin
    admin_auth = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"}).json()
    admin_headers = {"Authorization": f"Bearer {admin_auth['access_token']}"}
    admin_del = client.delete(f"/api/families/{fam_id}", headers=admin_headers)
    assert admin_del.status_code == 200

    print("[OK] Collector permissions & family/member management (View/Edit/Add allowed, Approve/Delete forbidden) passed")


if __name__ == "__main__":
    print("\n--- Running System Integration Tests ---")
    test_login_and_roles()
    test_geographic_hierarchy()
    test_family_and_member_registration()
    test_collector_permissions_and_family_management()
    test_reporting_and_excel()
    test_offline_sync()
    test_user_management_crud()
    test_user_audit_logs()
    test_backup_and_restore()
    print("\n>>> ALL TESTS PASSED SUCCESSFULLY! <<<")

