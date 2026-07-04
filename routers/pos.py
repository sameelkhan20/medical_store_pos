from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import update
from pydantic import BaseModel
from typing import List
import uuid

from database.config import get_db
from models.inventory import Medicine
from models.billing import Bill, BillItem

router = APIRouter(prefix="/api/pos", tags=["Billing / POS"])

# Pydantic Schemas (Frontend se aane wala cart data)
class ItemScan(BaseModel):
    barcode: str
    quantity: int

class CheckoutRequest(BaseModel):
    items: List[ItemScan]
    discount: float = 0.0

# API Endpoint: Checkout Process & Bill Generation
@router.post("/checkout")
async def process_checkout(request: CheckoutRequest, db: AsyncSession = Depends(get_db)):
    if not request.items:
        raise HTTPException(status_code=400, detail="Cart bilkul khali hai!")

    total_amount = 0.0
    bill_items_to_add = []

    # 1. Har scanned item ko check karein aur stock verify karein
    for req_item in request.items:
        # Barcode ke zariye medicine dhundein
        result = await db.execute(select(Medicine).where(Medicine.barcode == req_item.barcode))
        medicine = result.scalars().first()

        if not medicine:
            raise HTTPException(status_code=404, detail=f"Barcode {req_item.barcode} wali medicine system mein nahi mili!")
        
        if medicine.stock_quantity < req_item.quantity:
            raise HTTPException(
                status_code=400, 
                detail=f"'{medicine.name}' ka stock kam hai! Sirf {medicine.stock_quantity} available hain."
            )

        # 2. Total calculate karein
        item_total = medicine.sale_price * req_item.quantity
        total_amount += item_total

        # Atomic stock deduction to prevent double-sell concurrency issues
        stmt = (
            update(Medicine)
            .where(Medicine.id == medicine.id)
            .where(Medicine.stock_quantity >= req_item.quantity)
            .values(stock_quantity=Medicine.stock_quantity - req_item.quantity)
        )
        update_result = await db.execute(stmt)
        if update_result.rowcount == 0:
            raise HTTPException(status_code=400, detail=f"'{medicine.name}' ka stock concurrently update ho gaya. Try again.")

        # Bill Item ka object banayein (Abhi save nahi kiya)
        bill_items_to_add.append(
            BillItem(
                medicine_id=medicine.id,
                quantity=req_item.quantity,
                price_per_unit=medicine.sale_price,
                cost_per_unit=medicine.purchase_price,
                total_price=item_total
            )
        )

    # 3. Final calculations
    final_amount = total_amount - request.discount
    
    # Bill ka apna ek unique barcode / number generate karein (Returns/Lookup ke liye)
    bill_number = f"BILL-{str(uuid.uuid4().int)[:8]}"

    # 4. Database mein naya Bill save karein
    new_bill = Bill(
        bill_number=bill_number,
        total_amount=total_amount,
        discount=request.discount,
        final_amount=final_amount
    )
    db.add(new_bill)
    await db.flush() # Flush karke new_bill.id mil jayegi, bina actual commit ke

    # 5. Saare Bill Items ko is naye Bill ki ID ke sath save karein
    for b_item in bill_items_to_add:
        b_item.bill_id = new_bill.id
        db.add(b_item)

    await db.commit() # Final commit ek sath (Bill + Items + Stock Update)
    await db.refresh(new_bill)

    return {
        "status": "success",
        "message": "Checkout successful aur stock update ho gaya!",
        "bill_number": new_bill.bill_number,
        "total": new_bill.total_amount,
        "discount": new_bill.discount,
        "final_amount": new_bill.final_amount
    }

@router.get("/bill/{bill_number}")
async def get_bill_receipt(bill_number: str, db: AsyncSession = Depends(get_db)):
    # 1. Bill fetch karein
    bill_query = await db.execute(select(Bill).where(Bill.bill_number == bill_number))
    bill = bill_query.scalars().first()
    if not bill:
        raise HTTPException(status_code=404, detail="Bill system mein nahi mila!")
    
    # 2. Bill ke items aur unki corresponding medicine ki details fetch karein
    items_query = await db.execute(
        select(BillItem, Medicine)
        .join(Medicine, BillItem.medicine_id == Medicine.id)
        .where(BillItem.bill_id == bill.id)
    )
    items_data = items_query.all()
    
    items_list = []
    for b_item, med in items_data:
        items_list.append({
            "name": med.name,
            "quantity": b_item.quantity,
            "price_per_unit": b_item.price_per_unit,
            "total_price": b_item.total_price
        })
        
    return {
        "bill_number": bill.bill_number,
        "date": bill.date_created,
        "total_amount": bill.total_amount,
        "discount": bill.discount,
        "final_amount": bill.final_amount,
        "items": items_list
    }

@router.post("/refund/{bill_number}")
async def refund_bill(bill_number: str, db: AsyncSession = Depends(get_db)):
    # 1. Fetch original bill
    result = await db.execute(select(Bill).where(Bill.bill_number == bill_number))
    original_bill = result.scalars().first()
    
    if not original_bill:
        raise HTTPException(status_code=404, detail="Original bill nahi mila.")
        
    refund_bill_number = f"REF-{original_bill.bill_number}"
    
    # Check if already refunded
    check_refund = await db.execute(select(Bill).where(Bill.bill_number == refund_bill_number))
    if check_refund.scalars().first():
        raise HTTPException(status_code=400, detail="Yeh bill pehle hi refund ho chuka hai.")

    # 2. Fetch original items
    items_query = await db.execute(select(BillItem).where(BillItem.bill_id == original_bill.id))
    original_items = items_query.scalars().all()
    
    # 3. Create negative bill
    refund_bill = Bill(
        bill_number=refund_bill_number,
        total_amount=-original_bill.total_amount,
        discount=-original_bill.discount,
        final_amount=-original_bill.final_amount
    )
    db.add(refund_bill)
    await db.flush()
    
    # 4. Create negative items and restore stock
    for item in original_items:
        # Restore stock
        stmt = (
            update(Medicine)
            .where(Medicine.id == item.medicine_id)
            .values(stock_quantity=Medicine.stock_quantity + item.quantity)
        )
        await db.execute(stmt)
        
        # Add refund item
        refund_item = BillItem(
            bill_id=refund_bill.id,
            medicine_id=item.medicine_id,
            quantity=-item.quantity,
            price_per_unit=item.price_per_unit,
            cost_per_unit=item.cost_per_unit,
            total_price=-item.total_price
        )
        db.add(refund_item)
        
    await db.commit()
    return {"status": "success", "message": f"Bill {bill_number} successfully refund ho gaya hai aur stock wapas add ho gaya hai."}