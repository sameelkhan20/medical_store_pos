from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import update
from pydantic import BaseModel, Field
from typing import List, Optional

from database.config import get_db
from models.customer import Customer, CustomerTransaction

router = APIRouter(prefix="/api/customers", tags=["Customers"])

class CustomerCreate(BaseModel):
    name: str
    phone: str

class CustomerPayment(BaseModel):
    amount: float = Field(gt=0)
    description: str = "Payment received"

@router.post("/")
async def add_customer(cust: CustomerCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Customer).where(Customer.phone == cust.phone))
    if result.scalars().first():
        raise HTTPException(status_code=400, detail="Is phone number se pehle hi customer maujood hai.")
    
    new_cust = Customer(name=cust.name, phone=cust.phone)
    db.add(new_cust)
    await db.commit()
    await db.refresh(new_cust)
    return new_cust

@router.get("/")
async def get_customers(search: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    query = select(Customer)
    if search:
        query = query.where(Customer.name.ilike(f"%{search}%") | Customer.phone.ilike(f"%{search}%"))
    result = await db.execute(query)
    return result.scalars().all()

@router.post("/{customer_id}/pay")
async def add_payment(customer_id: int, payment: CustomerPayment, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Customer).where(Customer.id == customer_id))
    cust = result.scalars().first()
    if not cust:
        raise HTTPException(status_code=404, detail="Customer nahi mila")
        
    # Add transaction
    txn = CustomerTransaction(
        customer_id=customer_id,
        amount=-payment.amount, # Negative because they are paying us (reducing debt)
        description=payment.description
    )
    db.add(txn)
    
    # Update balance using Atomic SQL
    stmt = (
        update(Customer)
        .where(Customer.id == customer_id)
        .values(balance=Customer.balance - payment.amount)
    )
    await db.execute(stmt)
    
    await db.commit()
    await db.refresh(cust)
    return {"status": "success", "message": "Payment record ho gayi", "new_balance": cust.balance}

@router.get("/{customer_id}/transactions")
async def get_transactions(customer_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(CustomerTransaction)
        .where(CustomerTransaction.customer_id == customer_id)
        .order_by(CustomerTransaction.id.desc())
        .limit(50)
    )
    return result.scalars().all()
