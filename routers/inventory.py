from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from pydantic import BaseModel
from typing import Optional, List
from datetime import date
import uuid

from database.config import get_db
from models.inventory import Medicine

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
    purchase_price: float
    sale_price: float
    stock_quantity: int = 0

class MedicineResponse(MedicineCreate):
    id: int
    barcode: str

    class Config:
        from_attributes = True

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
        raise HTTPException(status_code=400, detail="Yeh Barcode pehle se maujood hai!")

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