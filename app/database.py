import os
import tempfile
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# Resolve project root and pre-seeded database location
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
LOCAL_DB_FILE = os.path.join(PROJECT_ROOT, "people_count.db")

# Check if running in Vercel serverless environment
if os.getenv("VERCEL"):
    import shutil
    tmp_dir = tempfile.gettempdir()
    db_path = os.path.join(tmp_dir, "people_count.db")
    # Copy pre-seeded SQLite database to /tmp if it doesn't exist yet or is empty
    if os.path.exists(LOCAL_DB_FILE):
        try:
            if not os.path.exists(db_path) or os.path.getsize(db_path) < 1000:
                shutil.copyfile(LOCAL_DB_FILE, db_path)
                print(f"[Vercel Startup] Copied pre-seeded DB ({os.path.getsize(LOCAL_DB_FILE)} bytes) to {db_path}")
        except Exception as e:
            print(f"[Vercel Startup] Warning copying DB to /tmp: {e}")
    default_db = f"sqlite:///{db_path}"
else:
    default_db = f"sqlite:///{LOCAL_DB_FILE}"

DATABASE_URL = os.getenv("DATABASE_URL", default_db)
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
