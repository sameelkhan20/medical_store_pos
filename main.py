from fastapi import FastAPI, Request, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from database.config import engine, Base
import contextlib
import asyncio
import shutil
import datetime
import os
import secrets

security = HTTPBasic()

def verify_credentials(credentials: HTTPBasicCredentials = Depends(security)):
    # Hardcoded admin credentials for simple POS security
    correct_username = secrets.compare_digest(credentials.username, "admin")
    correct_password = secrets.compare_digest(credentials.password, "admin123")
    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username

# Background task for automated backups
async def auto_backup_task():
    while True:
        # Wait 12 hours before creating a backup
        await asyncio.sleep(43200)
        try:
            if not os.path.exists("backups"):
                os.makedirs("backups")
            now = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_name = f"backups/medical_store_backup_{now}.db"
            shutil.copy2("medical_store.db", backup_name)
            print(f"[{now}] Backup successful: {backup_name}")
        except Exception as e:
            print(f"Backup failed: {e}")

# Database Models taake tables auto-create hon
from models import inventory, billing

# Saare API Routers
from routers import inventory as inventory_router
from routers import pos as pos_router
from routers import reports as reports_router

@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Database connection aur tables create karna
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("Database tables created successfully! POS System is live.")
    
    # Start auto backup background task
    backup_task = asyncio.create_task(auto_backup_task())
    
    yield
    
    # Shutdown: Safely disconnect karna
    backup_task.cancel()
    await engine.dispose()

# FastAPI initialization
app = FastAPI(title="Medical Store POS System", lifespan=lifespan)

# CORS configuration (Taake local network par PC 2 browser se easily access kar sake)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Frontend (HTML/CSS/JS) ko serve karne ke liye ---
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# UI Routes (Updated Starlette Syntax) - Protected with Basic Auth
@app.get("/")
async def root(request: Request, username: str = Depends(verify_credentials)):
    return templates.TemplateResponse(request, "dashboard.html")

@app.get("/dashboard")
async def dashboard_ui(request: Request, username: str = Depends(verify_credentials)):
    return templates.TemplateResponse(request, "dashboard.html")

@app.get("/pos")
async def pos_ui(request: Request, username: str = Depends(verify_credentials)):
    return templates.TemplateResponse(request, "pos.html")

@app.get("/inventory")
async def inventory_ui(request: Request, username: str = Depends(verify_credentials)):
    return templates.TemplateResponse(request, "inventory.html")

@app.get("/reports")
async def reports_ui(request: Request, username: str = Depends(verify_credentials)):
    return templates.TemplateResponse(request, "reports.html")

@app.get("/receipt/{bill_number}")
async def receipt_ui(request: Request, bill_number: str, username: str = Depends(verify_credentials)):
    return templates.TemplateResponse(request, "receipt.html", {"bill_number": bill_number})
# -----------------------------------------------------------------

# API Routes ko main application ke sath jorna
app.include_router(inventory_router.router)
app.include_router(pos_router.router)
app.include_router(reports_router.router)