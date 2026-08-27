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
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))


@app.get("/", response_class=HTMLResponse)
async def serve_home(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")


@app.get("/print", response_class=HTMLResponse)
async def serve_print(request: Request):
    return templates.TemplateResponse(request=request, name="print_report.html")

