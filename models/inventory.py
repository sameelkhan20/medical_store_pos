from sqlalchemy import Column, Integer, String, Float, Date
from database.config import Base

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