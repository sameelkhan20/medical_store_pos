from fastapi import FastAPI, Request, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from database.config import engine, Base, get_db
from sqlalchemy.future import select
import contextlib
import asyncio
import shutil
import datetime
import os
import secrets
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from models.auth import User

security = HTTPBasic()

async def verify_credentials(credentials: HTTPBasicCredentials = Depends(security), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.username == credentials.username))
    user = result.scalars().first()
    
    if not user or user.password != credentials.password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return user

async def verify_admin(user: User = Depends(verify_credentials)):
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user

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
from models import inventory, billing, auth, customer, supplier

# Saare API Routers
from routers import inventory as inventory_router
from routers import pos as pos_router
from routers import reports as reports_router
from routers import customers as customers_router
from routers import suppliers as suppliers_router

@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Database connection aur tables create karna
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
    # Check if admin user exists, if not, create it
    async with engine.connect() as conn:
        from sqlalchemy import text
        result = await conn.execute(text("SELECT id FROM users WHERE username='admin'"))
        if not result.fetchone():
            await conn.execute(text("INSERT INTO users (username, password, role) VALUES ('admin', 'admin123', 'admin')"))
            await conn.execute(text("INSERT INTO users (username, password, role) VALUES ('cashier', 'cashier123', 'cashier')"))
            await conn.commit()

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
async def root(request: Request, user: User = Depends(verify_credentials)):
    return templates.TemplateResponse(request, "dashboard.html", {"user": user})

@app.get("/dashboard")
async def dashboard_ui(request: Request, user: User = Depends(verify_credentials)):
    return templates.TemplateResponse(request, "dashboard.html", {"user": user})

@app.get("/pos")
async def pos_ui(request: Request, user: User = Depends(verify_credentials)):
    return templates.TemplateResponse(request, "pos.html", {"user": user})

@app.get("/inventory")
async def inventory_ui(request: Request, user: User = Depends(verify_credentials)):
    return templates.TemplateResponse(request, "inventory.html", {"user": user})

@app.get("/reports")
async def reports_ui(request: Request, user: User = Depends(verify_credentials)):
    if user.role != "admin":
        return templates.TemplateResponse(request, "unauthorized.html", {"user": user})
    return templates.TemplateResponse(request, "reports.html", {"user": user})

@app.get("/customers")
async def customers_ui(request: Request, user: User = Depends(verify_credentials)):
    return templates.TemplateResponse(request, "customers.html", {"user": user})

@app.get("/suppliers")
async def suppliers_ui(request: Request, user: User = Depends(verify_credentials)):
    if user.role != "admin":
        return templates.TemplateResponse(request, "unauthorized.html", {"user": user})
    return templates.TemplateResponse(request, "suppliers.html", {"user": user})

@app.get("/receipt/{bill_number}")
async def receipt_ui(request: Request, bill_number: str, user: User = Depends(verify_credentials)):
    return templates.TemplateResponse(request, "receipt.html", {"bill_number": bill_number, "user": user})
# -----------------------------------------------------------------

# API Routes ko main application ke sath jorna (Protected!)
app.include_router(inventory_router.router, dependencies=[Depends(verify_credentials)])
app.include_router(pos_router.router, dependencies=[Depends(verify_credentials)])
app.include_router(customers_router.router, dependencies=[Depends(verify_credentials)])

# Admin-only APIs
app.include_router(reports_router.router, dependencies=[Depends(verify_admin)])
app.include_router(suppliers_router.router, dependencies=[Depends(verify_admin)])

@app.get("/api/backup")
async def download_backup(user: User = Depends(verify_credentials)):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")
    if os.path.exists("medical_store.db"):
        return FileResponse("medical_store.db", filename=f"medical_store_backup_{datetime.date.today()}.db")
    raise HTTPException(status_code=404, detail="Database file not found")