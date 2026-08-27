import sys
import os

root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware

from app.database import engine, Base
from app.seed import init_db_and_seed
from app.api import auth, geo, families, reports, sync

app = FastAPI(
    title="ប្រព័ន្ធគ្រប់គ្រងស្ថិតិប្រជាជន និងគ្រួសារកម្ពុជា (Cambodia Population & Family Census)",
    description="ប្រព័ន្ធគ្រប់គ្រងរដ្ឋបាលភូមិសាស្ត្រ ព័ត៌មានគ្រួសារ ចុះបញ្ជីសមាជិក របាយការណ៍ស្វ័យប្រវត្តិតាមស្តង់ដាររដ្ឋបាលកម្ពុជា និង Offline PWA Sync",
    version="1.0.0"
)

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

# Mount API routers
app.include_router(auth.router)
app.include_router(geo.router)
app.include_router(families.router)
app.include_router(reports.router)
app.include_router(sync.router)

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


@app.get("/", response_class=HTMLResponse)
async def serve_home(request: Request):
    index_file = os.path.join(templates_dir, "index.html")
    if os.path.exists(index_file):
        with open(index_file, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    if templates:
        return templates.TemplateResponse(request=request, name="index.html")
    return HTMLResponse(content="<h1>Cambodia Population System is Running</h1>", status_code=200)


@app.get("/print", response_class=HTMLResponse)
async def serve_print(request: Request):
    print_file = os.path.join(templates_dir, "print_report.html")
    if os.path.exists(print_file):
        with open(print_file, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    if templates:
        return templates.TemplateResponse(request=request, name="print_report.html")
    return HTMLResponse(content="<h1>Print Report</h1>", status_code=200)

