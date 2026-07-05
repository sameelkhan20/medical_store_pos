from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from database.config import Base
import datetime

class Bill(Base):
    __tablename__ = "bills"

    id = Column(Integer, primary_key=True, index=True)
    # Bill ka apna barcode for easy lookup
    bill_number = Column(String, unique=True, index=True, nullable=False)
    date_created = Column(DateTime, default=datetime.datetime.now)
    total_amount = Column(Float, default=0.0)
    total_cost = Column(Float, default=0.0)
    discount = Column(Float, default=0.0)
    final_amount = Column(Float, default=0.0)
    payment_method = Column(String, default="cash")
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)

    # Ek bill mein multiple items ho sakte hain
    items = relationship("BillItem", back_populates="bill")

class BillItem(Base):
    __tablename__ = "bill_items"

    id = Column(Integer, primary_key=True, index=True)
    bill_id = Column(Integer, ForeignKey("bills.id"))
    medicine_id = Column(Integer, ForeignKey("medicines.id"))
    quantity = Column(Integer, nullable=False)
    price_per_unit = Column(Float, nullable=False)
    cost_per_unit = Column(Float, default=0.0)
    total_price = Column(Float, nullable=False)

    bill = relationship("Bill", back_populates="items")