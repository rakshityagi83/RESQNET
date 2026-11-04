from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import relationship

from database import Base


class Warehouse(Base):
    __tablename__ = "warehouses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(Text, nullable=False)
    state = Column(Text, nullable=False)
    district = Column(Text, nullable=False)
    latitude = Column(Float)
    longitude = Column(Float)
    verified_by = Column(Text, nullable=False)

    inventory = relationship(
        "Inventory",
        back_populates="warehouse",
        uselist=False,
    )


class Inventory(Base):
    __tablename__ = "inventory"

    warehouse_id = Column(
        Integer,
        ForeignKey("warehouses.id"),
        primary_key=True,
    )
    food = Column(Integer, nullable=False, default=0)
    water = Column(Integer, nullable=False, default=0)
    medicine = Column(Integer, nullable=False, default=0)

    warehouse = relationship(
        "Warehouse",
        back_populates="inventory",
    )


class Allocation(Base):
    __tablename__ = "allocations"

    id = Column(Text, primary_key=True)
    incident_id = Column(Text, nullable=False)
    warehouse_id = Column(Integer, nullable=False)
    requirements = Column(Text, nullable=False)
    status = Column(Text, nullable=False)
    created_at = Column(
        DateTime,
        server_default=func.current_timestamp(),
    )