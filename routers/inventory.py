from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import date
import uuid

from database.config import get_db
from models.inventory import Medicine, StockAdjustment, MedicineBatch
from sqlalchemy import update, func

router = APIRouter(prefix="/api/inventory", tags=["Inventory"])

# Pydantic Schemas (Data Validate karne ke liye)
class MedicineCreate(BaseModel):
    barcode: Optional[str] = None
    name: str
    generic_name: Optional[str] = None
    manufacturer: Optional[str] = None
    category: Optional[str] = None
    batch_number: Optional[str] = None
    expiry_date: Optional[date] = None
    purchase_price: float = Field(ge=0)
    sale_price: float = Field(ge=0)
    stock_quantity: int = Field(ge=0, default=0)

class MedicineResponse(MedicineCreate):
    id: int
    barcode: str

    class Config:
        from_attributes = True

class StockAdjustRequest(BaseModel):
    quantity_adjusted: int
    reason: str

# 1. API Endpoint: Nayi Medicine Add Karne Ke Liye
@router.post("/", response_model=MedicineResponse)
async def add_medicine(med: MedicineCreate, db: AsyncSession = Depends(get_db)):
    generated_barcode = med.barcode
    
    # Agar user ne barcode blank chhorh diya hai, toh automatically ek 12-digit barcode generate karo
    if not generated_barcode or generated_barcode.strip() == "":
        generated_barcode = str(uuid.uuid4().int)[:12]
    
    # Check karein ke kahin yeh barcode pehle se database mein toh nahi
    result = await db.execute(select(Medicine).where(Medicine.barcode == generated_barcode))
    existing_med = result.scalars().first()
    
    if existing_med:
        # Existing medicine hai toh naya batch add karo
        new_batch = MedicineBatch(
            medicine_id=existing_med.id,
            batch_number=med.batch_number,
            expiry_date=med.expiry_date,
            stock_quantity=med.stock_quantity
        )
        db.add(new_batch)
        
        # Total stock aur nearest expiry update karo
        existing_med.stock_quantity += med.stock_quantity
        
        if med.expiry_date:
            if not existing_med.expiry_date or med.expiry_date < existing_med.expiry_date:
                existing_med.expiry_date = med.expiry_date
                
        await db.commit()
        await db.refresh(existing_med)
        return existing_med
    else:
        # Nayi medicine database mein save karna
        new_medicine = Medicine(
            barcode=generated_barcode,
            name=med.name,
            generic_name=med.generic_name,
            manufacturer=med.manufacturer,
            category=med.category,
            batch_number=med.batch_number,
            expiry_date=med.expiry_date,
            purchase_price=med.purchase_price,
            sale_price=med.sale_price,
            stock_quantity=med.stock_quantity
        )
        db.add(new_medicine)
        await db.flush() # Naya ID lene ke liye
        
        # Iska pehla batch save karna
        new_batch = MedicineBatch(
            medicine_id=new_medicine.id,
            batch_number=med.batch_number,
            expiry_date=med.expiry_date,
            stock_quantity=med.stock_quantity
        )
        db.add(new_batch)
        
        await db.commit()
        await db.refresh(new_medicine)
        return new_medicine

# 2. API Endpoint: Saari Medicines Ki List Dekhne Ke Liye
@router.get("/", response_model=List[MedicineResponse])
async def get_medicines(
    skip: int = 0, 
    limit: int = 100, 
    search_query: Optional[str] = None, 
    db: AsyncSession = Depends(get_db)
):
    query = select(Medicine).where(Medicine.is_deleted == 0)
    
    if search_query:
        # SQLite mein ilike natively kaam karta hai case-insensitive search ke liye
        query = query.where(Medicine.name.ilike(f"%{search_query}%") | Medicine.barcode.ilike(f"%{search_query}%"))
        
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()

# 3. API Endpoint: Soft Delete Medicine
@router.delete("/{medicine_id}")
async def delete_medicine(medicine_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Medicine).where(Medicine.id == medicine_id))
    medicine = result.scalars().first()
    if not medicine:
        raise HTTPException(status_code=404, detail="Medicine system mein nahi mili")
    
    medicine.is_deleted = 1
    await db.commit()
    return {"status": "success", "message": "Medicine successfully delete ho gayi"}

# 4. API Endpoint: Stock Adjustment (Write-off)
@router.post("/{medicine_id}/adjust")
async def adjust_stock(medicine_id: int, req: StockAdjustRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Medicine).where(Medicine.id == medicine_id))
    medicine = result.scalars().first()
    if not medicine:
        raise HTTPException(status_code=404, detail="Medicine nahi mili")
        
    if medicine.stock_quantity + req.quantity_adjusted < 0:
        raise HTTPException(status_code=400, detail="Stock negative nahi ho sakta")

    # Atomic Update Stock (Main Table)
    stmt = (
        update(Medicine)
        .where(Medicine.id == medicine_id)
        .where(Medicine.stock_quantity + req.quantity_adjusted >= 0)
        .values(stock_quantity=Medicine.stock_quantity + req.quantity_adjusted)
    )
    res = await db.execute(stmt)
    if res.rowcount == 0:
        raise HTTPException(status_code=400, detail="Stock concurrently modified. Please try again.")

    # Sync Batches to prevent drift
    if req.quantity_adjusted > 0:
        # Stock added: Create a generic adjustment batch
        from datetime import timedelta
        adj_batch = MedicineBatch(
            medicine_id=medicine_id,
            batch_number="ADJUST",
            expiry_date=date.today() + timedelta(days=365),
            stock_quantity=req.quantity_adjusted
        )
        db.add(adj_batch)
    elif req.quantity_adjusted < 0:
        # Stock removed: FIFO deduct from oldest batches
        remaining_qty = abs(req.quantity_adjusted)
        batches_query = await db.execute(
            select(MedicineBatch)
            .where(MedicineBatch.medicine_id == medicine_id)
            .where(MedicineBatch.stock_quantity > 0)
            .order_by(MedicineBatch.expiry_date.asc().nulls_last())
        )
        batches = batches_query.scalars().all()
        
        for batch in batches:
            if remaining_qty <= 0:
                break
            deduct_qty = min(batch.stock_quantity, remaining_qty)
            
            batch_stmt = (
                update(MedicineBatch)
                .where(MedicineBatch.id == batch.id)
                .where(MedicineBatch.stock_quantity >= deduct_qty)
                .values(stock_quantity=MedicineBatch.stock_quantity - deduct_qty)
            )
            batch_res = await db.execute(batch_stmt)
            if batch_res.rowcount > 0:
                remaining_qty -= deduct_qty
            else:
                raise HTTPException(status_code=400, detail="Batch stock concurrently modified. Please try again.")

    # Log Adjustment
    adj = StockAdjustment(
        medicine_id=medicine_id,
        quantity_adjusted=req.quantity_adjusted,
        reason=req.reason
    )
    db.add(adj)
    await db.commit()
    
    return {"status": "success", "message": "Stock adjust ho gaya!"}

# 5. API Endpoint: Substitute / Alternative Medicines
@router.get("/alternatives/{generic_name}", response_model=List[MedicineResponse])
async def get_alternatives(generic_name: str, db: AsyncSession = Depends(get_db)):
    if not generic_name or generic_name.lower() == 'null':
        return []
        
    query = select(Medicine).where(
        Medicine.is_deleted == 0,
        Medicine.generic_name.ilike(f"%{generic_name}%"),
        Medicine.stock_quantity > 0
    ).limit(10)
    
    result = await db.execute(query)
    return result.scalars().all()