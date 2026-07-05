from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from pydantic import BaseModel, Field
from typing import List, Optional

from database.config import get_db
from models.supplier import Supplier, SupplierTransaction

router = APIRouter(prefix="/api/suppliers", tags=["Suppliers"])

class SupplierCreate(BaseModel):
    name: str
    phone: Optional[str] = None
    company: Optional[str] = None

class SupplierPayment(BaseModel):
    amount: float = Field(gt=0)
    description: str = "Payment to supplier"

@router.post("/")
async def add_supplier(sup: SupplierCreate, db: AsyncSession = Depends(get_db)):
    new_sup = Supplier(name=sup.name, phone=sup.phone, company=sup.company)
    db.add(new_sup)
    await db.commit()
    await db.refresh(new_sup)
    return new_sup

@router.get("/")
async def get_suppliers(search: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    query = select(Supplier)
    if search:
        query = query.where(Supplier.name.ilike(f"%{search}%") | Supplier.company.ilike(f"%{search}%"))
    result = await db.execute(query)
    return result.scalars().all()

@router.post("/{supplier_id}/pay")
async def pay_supplier(supplier_id: int, payment: SupplierPayment, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Supplier).where(Supplier.id == supplier_id))
    sup = result.scalars().first()
    if not sup:
        raise HTTPException(status_code=404, detail="Supplier nahi mila")
        
    txn = SupplierTransaction(
        supplier_id=supplier_id,
        amount=-payment.amount, # Negative because we are paying them (reducing our debt)
        description=payment.description
    )
    db.add(txn)
    
    # Update balance using Atomic SQL
    stmt = (
        update(Supplier)
        .where(Supplier.id == supplier_id)
        .values(balance=Supplier.balance - payment.amount)
    )
    await db.execute(stmt)
    
    await db.commit()
    await db.refresh(sup)
    return {"status": "success", "message": "Supplier payment record ho gayi", "new_balance": sup.balance}
