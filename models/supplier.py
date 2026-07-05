from sqlalchemy import Column, Integer, String, Float, ForeignKey
from database.config import Base
import datetime

class Supplier(Base):
    __tablename__ = "suppliers"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, index=True)
    phone = Column(String, nullable=True)
    company = Column(String, nullable=True)
    balance = Column(Float, default=0.0) # Positive means we owe them money
    date_added = Column(String, default=lambda: str(datetime.date.today()))

class SupplierTransaction(Base):
    __tablename__ = "supplier_transactions"
    
    id = Column(Integer, primary_key=True, index=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=False)
    amount = Column(Float, nullable=False) # Positive = we bought stock (debt increased), Negative = we paid them (debt decreased)
    description = Column(String, nullable=False)
    date_created = Column(String, default=lambda: str(datetime.date.today()))
