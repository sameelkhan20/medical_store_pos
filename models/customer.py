from sqlalchemy import Column, Integer, String, Float, ForeignKey
from database.config import Base
import datetime

class Customer(Base):
    __tablename__ = "customers"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, index=True)
    phone = Column(String, unique=True, index=True, nullable=False)
    balance = Column(Float, default=0.0) # Positive means they owe us money
    date_added = Column(String, default=lambda: str(datetime.date.today()))

class CustomerTransaction(Base):
    __tablename__ = "customer_transactions"
    
    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    amount = Column(Float, nullable=False) # Positive = credit/udhar taken, Negative = payment received
    description = Column(String, nullable=False)
    date_created = Column(String, default=lambda: str(datetime.date.today()))
