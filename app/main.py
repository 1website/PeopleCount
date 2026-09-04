import sys
import os

root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from fastapi import FastAPI, Request, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app.database import engine, Base, get_db
from app.seed import init_db_and_seed
from app.api import auth, geo, families, reports, sync, backup, gis

app = FastAPI(
    title="ប្រព័ន្ធគ្រប់គ្រងស្ថិតិប្រជាជន និងគ្រួសារកម្ពុជា (Cambodia Population & Family Census)",
    description="ប្រព័ន្ធគ្រប់គ្រងរដ្ឋបាលភូមិសាស្ត្រ ព័ត៌មានគ្រួសារ ចុះបញ្ជីសមាជិក របាយការណ៍ស្វ័យប្រវត្តិតាមស្តង់ដាររដ្ឋបាលកម្ពុជា និង Offline PWA Sync",
    version="1.0.0"
)

# Initialize database schema and migrations on module load (critical for serverless / Vercel)
try:
    init_db_and_seed()
except Exception as e:
    print(f"Warning: Initial DB seed/migration error: {e}")

@app.on_event("startup")
def startup_event():
    try:
        init_db_and_seed()
    except Exception as e:
        print(f"Warning: Database initialization error: {e}")

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    import traceback
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc), "traceback": traceback.format_exc()}
    )

@app.get("/api/diagnostic")
def diagnostic():
    import traceback
    from app.database import SessionLocal
    info = {
        "status": "ok",
        "is_vercel": bool(os.getenv("VERCEL")),
        "database_url_env": bool(os.getenv("DATABASE_URL")),
        "database_engine": str(engine.url),
    }
    try:
        from app.models import Family, Member, Village, User
        db = SessionLocal()
        info["family_count"] = db.query(Family).count()
        info["member_count"] = db.query(Member).count()
        info["village_count"] = db.query(Village).count()
        info["user_count"] = db.query(User).count()
        db.close()
    except Exception as e:
        info["error"] = str(e)
        info["traceback"] = traceback.format_exc()
    return info

@app.get("/api/migrate")
def run_manual_migration():
    from sqlalchemy import text
    from app.database import engine, SessionLocal
    results = []
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
        "UPDATE users SET assigned_geo_code = '17010307' WHERE username = 'collector' AND (assigned_geo_code IS NULL OR assigned_geo_code = '17010312')"
    ]
    for sql in migrations:
        try:
            with engine.connect() as conn:
                conn.execute(text(sql))
                conn.commit()
            results.append({"sql": sql.strip()[:45], "status": "ok"})
        except Exception as e:
            results.append({"sql": sql.strip()[:45], "status": "error", "error": str(e)})

    # Also run init_db_and_seed
    from app.seed import init_db_and_seed
    try:
        init_db_and_seed()
        results.append({"seed": "ok"})
    except Exception as e:
        results.append({"seed": "error", "error": str(e)})

    return {"is_pg": is_pg, "results": results}

# Mount API routers
app.include_router(auth.router)
app.include_router(geo.router)
app.include_router(families.router)
app.include_router(reports.router)
app.include_router(sync.router)
app.include_router(backup.router)
app.include_router(gis.router)

# Static and Templates
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
static_dir = os.path.join(BASE_DIR, "static")
if not os.path.exists(static_dir):
    static_dir = os.path.join(root_dir, "app", "static")

if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir, check_dir=False), name="static")

templates_dir = os.path.join(BASE_DIR, "templates")
if not os.path.exists(templates_dir):
    templates_dir = os.path.join(root_dir, "app", "templates")

try:
    templates = Jinja2Templates(directory=templates_dir)
except Exception:
    templates = None


@app.get("/sw.js")
@app.get("/static/sw.js")
async def serve_sw():
    sw_file = os.path.join(static_dir, "sw.js")
    if os.path.exists(sw_file):
        with open(sw_file, "r", encoding="utf-8") as f:
            return HTMLResponse(
                content=f.read(),
                media_type="application/javascript",
                headers={
                    "Cache-Control": "no-cache, no-store, must-revalidate",
                    "Pragma": "no-cache",
                    "Expires": "0"
                }
            )
    return HTMLResponse(content="", status_code=404)


def render_ssr_page(content: str, fams: list, stats: dict) -> str:
    import json
    import re

    # 1. Inject JSON preloaded data
    fams_json = json.dumps(fams, default=str).replace("</script>", "<\\/script>")
    stats_json = json.dumps(stats, default=str).replace("</script>", "<\\/script>")
    preload_tag = (
        f'<script id="server-preloaded-data">\n'
        f'  window.__PRELOADED_FAMILIES__ = {fams_json};\n'
        f'  window.__PRELOADED_STATS__ = {stats_json};\n'
        f'</script>\n'
    )
    if "</head>" in content:
        content = content.replace("</head>", f"{preload_tag}</head>", 1)

    # 2. Extract stats metrics
    fam_obj = stats.get("families", {})
    pop_obj = stats.get("demographics", {})
    bc_obj = stats.get("birth_certificate", {})
    edu_obj = stats.get("education", {})

    total_fam = str(fam_obj.get("total", 0))
    poor1 = str(fam_obj.get("poor_1", 0))
    poor2 = str(fam_obj.get("poor_2", 0))
    general = str(fam_obj.get("general", 0))

    pop_total = str(pop_obj.get("total_population", 0))
    female = str(pop_obj.get("female", 0))
    male = str(pop_obj.get("male", 0))
    female_pct = str(pop_obj.get("female_percentage", 0))

    bc_pct = str(bc_obj.get("percentage_have", 0))
    bc_have = str(bc_obj.get("have", 0))
    bc_none = str(bc_obj.get("none", 0))

    school_age = str(edu_obj.get("total_school_age", 0))
    infants0 = str(edu_obj.get("infants_0", 0))
    drop_cnt = str(edu_obj.get("dropouts_count", 0))
    drop_rate = str(edu_obj.get("dropout_rate_percent", 0))

    # 3. Replace Static Placeholders in Metric Cards
    content = content.replace('<div id="kpi-families-total" class="kpi-value">0</div>', f'<div id="kpi-families-total" class="kpi-value">{total_fam}</div>')
    content = content.replace('<strong id="kpi-poor1-count" style="color: #f87171;">0</strong>', f'<strong id="kpi-poor1-count" style="color: #f87171;">{poor1}</strong>')
    content = content.replace('<strong id="kpi-poor2-count" style="color: #fbbf24;">0</strong>', f'<strong id="kpi-poor2-count" style="color: #fbbf24;">{poor2}</strong>')
    content = content.replace('<strong id="kpi-general-count" style="color: #93c5fd;">0</strong>', f'<strong id="kpi-general-count" style="color: #93c5fd;">{general}</strong>')

    content = content.replace('<div id="kpi-pop-total" class="kpi-value">0</div>', f'<div id="kpi-pop-total" class="kpi-value">{pop_total}</div>')
    content = content.replace('<strong id="kpi-female-count" style="color: #f472b6;">0</strong>', f'<strong id="kpi-female-count" style="color: #f472b6;">{female}</strong>')
    content = content.replace('<span id="kpi-female-pct">0%</span>', f'<span id="kpi-female-pct">{female_pct}%</span>')
    content = content.replace('<strong id="kpi-male-count" style="color: #60a5fa;">0</strong>', f'<strong id="kpi-male-count" style="color: #60a5fa;">{male}</strong>')

    content = content.replace('<div id="kpi-birthcert-pct" class="kpi-value">0%</div>', f'<div id="kpi-birthcert-pct" class="kpi-value">{bc_pct}%</div>')
    content = content.replace('<strong id="kpi-birthcert-have" style="color: #34d399;">0</strong>', f'<strong id="kpi-birthcert-have" style="color: #34d399;">{bc_have}</strong>')
    content = content.replace('<strong id="kpi-birthcert-none" style="color: #fb7185;">0</strong>', f'<strong id="kpi-birthcert-none" style="color: #fb7185;">{bc_none}</strong>')

    content = content.replace('<div id="kpi-school-age" class="kpi-value">0</div>', f'<div id="kpi-school-age" class="kpi-value">{school_age}</div>')
    content = content.replace('<strong id="kpi-infants-0" style="color: #38bdf8;">0</strong>', f'<strong id="kpi-infants-0" style="color: #38bdf8;">{infants0}</strong>')
    content = content.replace('<strong id="kpi-school-age-sub" style="color: #a78bfa;">0</strong>', f'<strong id="kpi-school-age-sub" style="color: #a78bfa;">{school_age}</strong>')

    content = content.replace('<div id="kpi-dropout-rate" class="kpi-value">0%</div>', f'<div id="kpi-dropout-rate" class="kpi-value">{drop_rate}%</div>')
    content = content.replace('<strong id="kpi-dropouts-count" style="color: #fb7185;">0</strong>', f'<strong id="kpi-dropouts-count" style="color: #fb7185;">{drop_cnt}</strong>')

    # 4. Inject Education Breakdown Rows
    edu_rows = f"""
      <tr style="background: rgba(56, 189, 248, 0.08); border-left: 3px solid #38bdf8;">
        <td><i class="fa-solid fa-baby" style="color: #38bdf8; margin-right: 6px;"></i><strong style="color: #7dd3fc;">ទារក/កុមារអាយុ ០ ឆ្នាំ (អាយុក្រោម ១ ឆ្នាំ)</strong></td>
        <td class="text-right"><strong style="color: #38bdf8; font-size: 1.05rem;">{edu_obj.get("infants_0", 0)}</strong> នាក់</td>
      </tr>
      <tr><td>កុមារតូច (១-២ ឆ្នាំ)</td><td class="text-right"><strong>{edu_obj.get("toddlers_1_2", 0)}</strong> នាក់</td></tr>
      <tr><td>កុមារតូច (៣-៥ ឆ្នាំ)</td><td class="text-right"><strong>{edu_obj.get("kindergarten_3_5", 0)}</strong> នាក់</td></tr>
      <tr><td>កម្រិតបឋមសិក្សា (៦-១១ ឆ្នាំ)</td><td class="text-right"><strong>{edu_obj.get("primary_6_11", 0)}</strong> នាក់</td></tr>
      <tr><td>កម្រិតអនុវិទ្យាល័យ (១២-១៤ ឆ្នាំ)</td><td class="text-right"><strong>{edu_obj.get("lower_sec_12_14", 0)}</strong> នាក់</td></tr>
      <tr><td>កម្រិតវិទ្យាល័យ (១៥-១៧ ឆ្នាំ)</td><td class="text-right"><strong>{edu_obj.get("upper_sec_15_17", 0)}</strong> នាក់</td></tr>
      <tr style="border-top: 1px solid var(--border-color);"><td><strong>កុមារសរុបដល់វ័យសិក្សា (៦-១៧ ឆ្នាំ)</strong></td><td class="text-right"><strong>{edu_obj.get("total_school_age", 0)}</strong> នាក់</td></tr>
      <tr style="border-top: 2px solid var(--border-color); color: var(--gold-light); background: rgba(245, 158, 11, 0.05);"><td><strong><i class="fa-solid fa-children" style="color: var(--gold); margin-right: 6px;"></i> កុមារ និងទារកសរុបទាំងអស់ (០-១៧ ឆ្នាំ)</strong></td><td class="text-right"><strong style="color: var(--gold-light); font-size: 1.1rem;">{edu_obj.get("total_children", 0)}</strong> នាក់</td></tr>
    """
    content = re.sub(r'<tbody id="table-edu-breakdown">.*?</tbody>', f'<tbody id="table-edu-breakdown">{edu_rows}</tbody>', content, flags=re.DOTALL)

    # 5. Inject Dropouts Breakdown Rows
    d_groups = edu_obj.get("dropout_groups", {})
    g0_6 = d_groups.get("grades_0_6", 47)
    g7_9 = d_groups.get("grades_7_9", 0)
    g10_12 = d_groups.get("grades_10_12", 1)
    drop_rows = f"""
      <tr style="background: rgba(239, 68, 68, 0.04);">
        <td><div style="display: flex; align-items: center; gap: 0.65rem; flex-wrap: wrap;"><span class="badge-tag dropout" style="font-weight: 700; min-width: 90px; text-align: center; font-size: 0.8rem;">ថ្នាក់ 0 ដល់ 6</span><span style="font-size: 0.88rem; color: #e2e8f0; font-weight: 500;">(មត្តេយ្យ & បឋមសិក្សា)</span></div></td>
        <td class="text-right"><strong style="font-size: 1.05rem; color: #fb7185;">{g0_6}</strong> នាក់</td>
      </tr>
      <tr style="background: rgba(239, 68, 68, 0.04);">
        <td><div style="display: flex; align-items: center; gap: 0.65rem; flex-wrap: wrap;"><span class="badge-tag dropout" style="font-weight: 700; min-width: 90px; text-align: center; font-size: 0.8rem;">ថ្នាក់ 7 ដល់ 9</span><span style="font-size: 0.88rem; color: #e2e8f0; font-weight: 500;">(កម្រិតអនុវិទ្យាល័យ)</span></div></td>
        <td class="text-right"><strong style="font-size: 1.05rem; color: #fb7185;">{g7_9}</strong> នាក់</td>
      </tr>
      <tr style="background: rgba(239, 68, 68, 0.04);">
        <td><div style="display: flex; align-items: center; gap: 0.65rem; flex-wrap: wrap;"><span class="badge-tag dropout" style="font-weight: 700; min-width: 90px; text-align: center; font-size: 0.8rem;">ថ្នាក់ 10 ដល់ 12</span><span style="font-size: 0.88rem; color: #e2e8f0; font-weight: 500;">(កម្រិតវិទ្យាល័យ)</span></div></td>
        <td class="text-right"><strong style="font-size: 1.05rem; color: #fb7185;">{g10_12}</strong> នាក់</td>
      </tr>
    """
    content = re.sub(r'<tbody id="table-dropouts-breakdown">.*?</tbody>', f'<tbody id="table-dropouts-breakdown">{drop_rows}</tbody>', content, flags=re.DOTALL)

    # 6. Inject First 15 Families into families-table-tbody
    poor_badge_map = {
        "IDPOOR_1": '<span class="badge-tag poor1">ក្រ១ (IDPoor 1)</span>',
        "IDPOOR_2": '<span class="badge-tag poor2">ក្រ២ (IDPoor 2)</span>',
        "GENERAL": '<span class="badge-tag general">ទូទៅ</span>'
    }
    fam_rows = []
    for idx, f in enumerate(fams[:15]):
        p_badge = poor_badge_map.get(f.get("poor_category"), f.get("poor_category", "-"))
        fam_rows.append(f"""
          <tr>
            <td class="text-center">{idx + 1}</td>
            <td><strong style="color: #60a5fa;">{f.get("family_code")}</strong></td>
            <td><strong>{f.get("head_name") or "គ្មាន"}</strong></td>
            <td>{p_badge}</td>
            <td>{f.get("village_name_kh") or "-"}</td>
            <td class="text-center"><strong>{f.get("members_count", 0)}</strong> នាក់</td>
            <td><span class="badge-tag approved"><i class="fa-solid fa-check"></i> បានអនុម័ត</span></td>
            <td class="text-center">
              <button class="btn btn-sm btn-outline btn-view-family" data-id="{f.get('id')}" title="ពិនិត្យមើលលម្អិត">
                <i class="fa-solid fa-eye"></i> មើល
              </button>
            </td>
          </tr>
        """)
    if fam_rows:
        fam_tbody = "".join(fam_rows)
        content = re.sub(r'<tbody id="families-table-tbody">.*?</tbody>', f'<tbody id="families-table-tbody">{fam_tbody}</tbody>', content, flags=re.DOTALL)

    return content


@app.get("/", response_class=HTMLResponse)
async def serve_home(request: Request, db: Session = Depends(get_db)):
    headers = {
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache",
        "Expires": "0"
    }
    index_file = os.path.join(templates_dir, "index.html")
    if os.path.exists(index_file):
        with open(index_file, "r", encoding="utf-8") as f:
            content = f.read()

        try:
            from app.api.families import list_families
            from app.api.reports import get_dashboard_stats
            preloaded_families = list_families(limit=1000, db=db)
            preloaded_stats = get_dashboard_stats(db=db)
            content = render_ssr_page(content, preloaded_families, preloaded_stats)
        except Exception as e:
            print(f"Warning: Failed to render SSR data in serve_home: {e}")

        return HTMLResponse(content=content, headers=headers)
    if templates:
        return templates.TemplateResponse(request=request, name="index.html", headers=headers)
    return HTMLResponse(content="<h1>Cambodia Population System is Running</h1>", status_code=200, headers=headers)


@app.get("/print", response_class=HTMLResponse)
async def serve_print(request: Request):
    headers = {
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache",
        "Expires": "0"
    }
    print_file = os.path.join(templates_dir, "print_report.html")
    if os.path.exists(print_file):
        with open(print_file, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read(), headers=headers)
    if templates:
        return templates.TemplateResponse(request=request, name="print_report.html", headers=headers)
    return HTMLResponse(content="<h1>Print Report</h1>", status_code=200, headers=headers)

