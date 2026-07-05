from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import update
from pydantic import BaseModel, Field
from typing import List
import uuid

from database.config import get_db
from models.inventory import Medicine, MedicineBatch
from models.billing import Bill, BillItem
from models.customer import Customer, CustomerTransaction

router = APIRouter(prefix="/api/pos", tags=["Billing / POS"])

# Pydantic Schemas (Frontend se aane wala cart data)
class ItemScan(BaseModel):
    barcode: str
    quantity: int = Field(gt=0)

class CheckoutRequest(BaseModel):
    items: List[ItemScan]
    discount: float = Field(ge=0, default=0.0)
    payment_method: str = "cash"
    customer_phone: str = None

# API Endpoint: Checkout Process & Bill Generation
@router.post("/checkout")
async def process_checkout(request: CheckoutRequest, db: AsyncSession = Depends(get_db)):
    if not request.items:
        raise HTTPException(status_code=400, detail="Cart bilkul khali hai!")

    total_amount = 0.0
    total_cost_acc = 0.0
    bill_items_to_add = []

    # 1. Har scanned item ko check karein aur stock verify karein
    for req_item in request.items:
        # Barcode ke zariye medicine dhundein (ensure is_deleted == 0)
        result = await db.execute(
            select(Medicine)
            .where(Medicine.barcode == req_item.barcode, Medicine.is_deleted == 0)
        )
        medicine = result.scalars().first()

        if not medicine:
            raise HTTPException(status_code=404, detail=f"Barcode {req_item.barcode} wali dawai system mein available nahi (ya delete ho chuki hai)!")
        
        if medicine.stock_quantity < req_item.quantity:
            raise HTTPException(
                status_code=400, 
                detail=f"'{medicine.name}' ka stock kam hai! Sirf {medicine.stock_quantity} available hain."
            )

        # 2. Total calculate karein
        item_total = medicine.sale_price * req_item.quantity
        item_cost = medicine.purchase_price * req_item.quantity
        total_amount += item_total
        total_cost_acc += item_cost

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

        # Batch-level FIFO deduction
        remaining_qty = req_item.quantity
        batches_query = await db.execute(
            select(MedicineBatch)
            .where(MedicineBatch.medicine_id == medicine.id)
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
            batch_update_result = await db.execute(batch_stmt)
            
            if batch_update_result.rowcount > 0:
                remaining_qty -= deduct_qty
            else:
                raise HTTPException(status_code=400, detail="Stock concurrently modified during batch deduction. Please try again.")

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
    if request.discount > total_amount:
        raise HTTPException(status_code=400, detail="Discount total amount se zyada nahi ho sakta!")
        
    final_amount = total_amount - request.discount
    
    # Bill ka apna ek unique barcode / number generate karein (Returns/Lookup ke liye)
    bill_number = f"BILL-{str(uuid.uuid4().int)[:8]}"

    # 4. Database mein naya Bill save karein
    new_bill = Bill(
        bill_number=bill_number,
        total_amount=total_amount,
        total_cost=total_cost_acc,
        discount=request.discount,
        final_amount=final_amount,
        payment_method=request.payment_method
    )
    db.add(new_bill)
    await db.flush() # ID lene ke liye

    # 5. Saare Bill Items ko is naye Bill ki ID ke sath save karein
    for b_item in bill_items_to_add:
        b_item.bill_id = new_bill.id
        db.add(b_item)

    # 6. Udhar Khata Management
    if request.payment_method == "udhar" and request.customer_phone:
        cust_query = await db.execute(select(Customer).where(Customer.phone == request.customer_phone))
        cust = cust_query.scalars().first()
        if not cust:
            raise HTTPException(status_code=400, detail="Udhar ke liye Customer pehle se register hona zaroori hai.")
        
        new_bill.customer_id = cust.id
        
        # Atomic balance update
        stmt = (
            update(Customer)
            .where(Customer.id == cust.id)
            .values(balance=Customer.balance + final_amount)
        )
        await db.execute(stmt)
        
        txn = CustomerTransaction(
            customer_id=cust.id,
            amount=final_amount,
            description=f"Bill udhar: {bill_number}"
        )
        db.add(txn)

    await db.commit() # Final commit ek sath (Bill + Items + Stock Update + Khata)
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
        total_cost=-original_bill.total_cost,
        discount=-original_bill.discount,
        final_amount=-original_bill.final_amount,
        payment_method=original_bill.payment_method,
        customer_id=original_bill.customer_id
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
        
        # Add refunded item to a special REFUND batch with +1 year expiry
        from datetime import date, timedelta
        default_expiry = date.today() + timedelta(days=365)
        refund_batch = MedicineBatch(
            medicine_id=item.medicine_id,
            batch_number=f"REF-{bill_number}",
            expiry_date=default_expiry,
            stock_quantity=item.quantity
        )
        db.add(refund_batch)
        
    # 5. Khata Sync: Agar original bill udhar tha, toh balance wapas karo
    if original_bill.payment_method == "udhar" and original_bill.customer_id:
        cust_query = await db.execute(select(Customer).where(Customer.id == original_bill.customer_id))
        cust = cust_query.scalars().first()
        if cust:
            # Atomic balance update
            stmt = (
                update(Customer)
                .where(Customer.id == cust.id)
                .values(balance=Customer.balance - original_bill.final_amount)
            )
            await db.execute(stmt)
            
            txn = CustomerTransaction(
                customer_id=cust.id,
                amount=-original_bill.final_amount,
                description=f"Refund: {bill_number}"
            )
            db.add(txn)

    await db.commit()
    return {"status": "success", "message": f"Bill {bill_number} successfully refund ho gaya hai aur stock wapas add ho gaya hai."}