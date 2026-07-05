from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func
from datetime import date, timedelta
import datetime
from fastapi.responses import StreamingResponse
import io
import csv

from database.config import get_db
from models.inventory import Medicine
from models.billing import Bill

router = APIRouter(prefix="/api/reports", tags=["Reports & Alerts"])

# 1. API Endpoint: Dashboard Stats (Quick Snapshot)
@router.get("/dashboard")
async def get_dashboard_stats(db: AsyncSession = Depends(get_db)):
    today = date.today()
    thirty_days_from_now = today + timedelta(days=30)

    # Aaj ki sales, profit, aur bills count
    bills_query = await db.execute(
        select(func.sum(Bill.final_amount), func.sum(Bill.total_cost), func.count(Bill.id))
        # SQLite mein date compare karne ke liye string format use karna safe hai
        .where(func.date(Bill.date_created) == str(today))
    )
    sales_data = bills_query.first()
    today_sales = sales_data[0] or 0.0
    today_cost = sales_data[1] or 0.0
    today_bills = sales_data[2] or 0
    today_profit = today_sales - today_cost

    # Low stock count (Misal ke tor par 10 se kam stock ho toh alert)
    low_stock_query = await db.execute(
        select(func.count(Medicine.id))
        .where(Medicine.stock_quantity <= 10)
        .where(Medicine.is_deleted == 0)
    )
    low_stock_count = low_stock_query.scalar() or 0

    # Expiring items count (Agley 30 din mein)
    expiring_query = await db.execute(
        select(func.count(Medicine.id))
        .where(Medicine.is_deleted == 0)
        .where(Medicine.expiry_date != None)
        .where(Medicine.expiry_date <= thirty_days_from_now)
    )
    expiring_count = expiring_query.scalar() or 0

    return {
        "today_sales": today_sales,
        "today_profit": today_profit,
        "today_bills_count": today_bills,
        "low_stock_count": low_stock_count,
        "expiring_items_count": expiring_count
    }

@router.get("/export")
async def export_sales_csv(db: AsyncSession = Depends(get_db)):
    async def csv_generator():
        output = io.StringIO()
        writer = csv.writer(output)
        # Write header
        writer.writerow(["Bill ID", "Bill Number", "Date", "Discount", "Total Cost", "Final Amount", "Profit"])
        yield output.getvalue()
        output.seek(0)
        output.truncate(0)

        # Stream rows from DB to avoid OOM
        result = await db.stream(select(Bill))
        async for b in result.scalars():
            profit = b.final_amount - (b.total_cost or 0.0)
            writer.writerow([b.id, b.bill_number, b.date_created, b.discount, b.total_cost, b.final_amount, profit])
            yield output.getvalue()
            output.seek(0)
            output.truncate(0)

    return StreamingResponse(
        csv_generator(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=sales_report.csv"}
    )

# 2. API Endpoint: Low Stock Medicines List
@router.get("/low-stock")
async def get_low_stock_list(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Medicine)
        .where(Medicine.stock_quantity <= 10)
        .where(Medicine.is_deleted == 0)
    )
    return result.scalars().all()

# 3. API Endpoint: Expiring Medicines List
@router.get("/expiring")
async def get_expiring_list(db: AsyncSession = Depends(get_db)):
    thirty_days_from_now = date.today() + timedelta(days=30)
    result = await db.execute(
        select(Medicine)
        .where(Medicine.is_deleted == 0)
        .where(Medicine.expiry_date != None)
        .where(Medicine.expiry_date <= thirty_days_from_now)
    )
    return result.scalars().all()

# 4. API Endpoint: Daily Sales History (Kisi bhi date ki)
@router.get("/sales/{target_date}")
async def get_sales_history(target_date: str, db: AsyncSession = Depends(get_db)):
    # target_date format: 'YYYY-MM-DD'
    result = await db.execute(
        select(Bill).where(func.date(Bill.date_created) == target_date)
    )
    bills = result.scalars().all()
    
    total_revenue = sum(bill.final_amount for bill in bills)
    total_profit = sum((bill.final_amount - bill.total_cost) for bill in bills)
    
    return {
        "date": target_date,
        "total_bills": len(bills),
        "total_revenue": total_revenue,
        "total_profit": total_profit,
        "bills": bills
    }