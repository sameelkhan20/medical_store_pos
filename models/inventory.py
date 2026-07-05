from sqlalchemy import Column, Integer, String, Float, Date
from database.config import Base
import datetime

class Medicine(Base):
    __tablename__ = "medicines"

    id = Column(Integer, primary_key=True, index=True)
    # Agar barcode nahi hoga toh backend auto-generate karke isme save karega
    barcode = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, index=True, nullable=False)
    generic_name = Column(String, index=True, nullable=True)
    manufacturer = Column(String, nullable=True)
    category = Column(String, nullable=True)
    batch_number = Column(String, nullable=True)
    expiry_date = Column(Date, nullable=True)
    purchase_price = Column(Float, nullable=False)
    sale_price = Column(Float, nullable=False)
    stock_quantity = Column(Integer, default=0)
    is_deleted = Column(Integer, default=0)  # Use Integer for Boolean compatibility in SQLite

class StockAdjustment(Base):
    __tablename__ = "stock_adjustments"

    id = Column(Integer, primary_key=True, index=True)
    medicine_id = Column(Integer, nullable=False, index=True)
    quantity_adjusted = Column(Integer, nullable=False) # Negative for damage/expiry, positive for correction
    reason = Column(String, nullable=False)
    date_created = Column(String, default=lambda: str(datetime.date.today()))

class MedicineBatch(Base):
    __tablename__ = "medicine_batches"

    id = Column(Integer, primary_key=True, index=True)
    medicine_id = Column(Integer, nullable=False, index=True)
    batch_number = Column(String, nullable=True)
    expiry_date = Column(Date, nullable=True)
    stock_quantity = Column(Integer, default=0)
    date_added = Column(String, default=lambda: str(datetime.date.today()))