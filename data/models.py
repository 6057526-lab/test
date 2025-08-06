"""
Модели данных для БД хоккейной экипировки
"""
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime,
    ForeignKey, UniqueConstraint, CheckConstraint, Text
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from data.db import Base


class Agent(Base):
    """Продавцы/агенты"""
    __tablename__ = 'agents'

    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True, nullable=False)
    telegram_username = Column(String(100))
    full_name = Column(String(200), nullable=False)
    is_admin = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Связи
    sales = relationship("Sale", back_populates="agent")
    bonuses = relationship("Bonus", back_populates="agent")

    def __repr__(self):
        return f"<Agent({self.full_name}, @{self.telegram_username})>"


class Batch(Base):
    """Партии товаров"""
    __tablename__ = 'batches'

    id = Column(Integer, primary_key=True)
    batch_number = Column(String(50), unique=True, nullable=False)
    received_date = Column(DateTime, default=datetime.utcnow)
    warehouse = Column(String(100), nullable=False)
    created_by_id = Column(Integer, ForeignKey('agents.id'))

    # Связи
    products = relationship("Product", back_populates="batch")
    created_by = relationship("Agent")

    def __repr__(self):
        return f"<Batch({self.batch_number}, {self.received_date})>"


class Product(Base):
    """Товары"""
    __tablename__ = 'products'

    id = Column(Integer, primary_key=True)
    ean = Column(String(13), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    model = Column(String(100))
    color = Column(String(50))
    size = Column(String(20))
    age = Column(String(20))
    fit = Column(String(20))
    weight = Column(Float, nullable=False)

    # Финансовые поля
    quantity = Column(Integer, nullable=False)
    price_eur = Column(Float, nullable=False)
    exchange_rate = Column(Float, nullable=False)
    coefficient = Column(Float, nullable=False)
    logistics_per_kg = Column(Float, nullable=False)
    cost_price = Column(Float, nullable=False)  # Себестоимость в рублях
    retail_price = Column(Float)  # РРЦ в рублях

    # Связи
    batch_id = Column(Integer, ForeignKey('batches.id'), nullable=False)
    batch = relationship("Batch", back_populates="products")
    sales = relationship("Sale", back_populates="product")
    price_history = relationship("PriceHistory", back_populates="product")
    stock_logs = relationship("StockLog", back_populates="product")

    # Ограничения
    __table_args__ = (
        UniqueConstraint('ean', 'batch_id', name='unique_ean_per_batch'),
        CheckConstraint('quantity >= 0', name='check_quantity_positive'),
        CheckConstraint('price_eur >= 0', name='check_price_positive'),
        CheckConstraint('weight > 0', name='check_weight_positive'),
        CheckConstraint("fit IN ('regular', 'tapered', 'wide')", name='check_fit_type'),
    )

    def __repr__(self):
        return f"<Product({self.ean}, {self.name}, {self.size})>"

    @property
    def margin(self):
        """Маржа в рублях"""
        if self.retail_price:
            return self.retail_price - self.cost_price
        return 0

    @property
    def margin_percent(self):
        """Маржинальность в процентах (GM%)"""
        if self.retail_price and self.retail_price > 0:
            return (self.margin / self.retail_price) * 100
        return 0


class Sale(Base):
    """Продажи"""
    __tablename__ = 'sales'

    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey('products.id'), nullable=False)
    agent_id = Column(Integer, ForeignKey('agents.id'), nullable=False)
    quantity = Column(Integer, default=1, nullable=False)
    sale_price = Column(Float, nullable=False)
    margin = Column(Float, nullable=False)
    margin_percent = Column(Float, nullable=False)
    warehouse = Column(String(100), nullable=False)
    sale_date = Column(DateTime, default=datetime.utcnow)
    is_returned = Column(Boolean, default=False)
    returned_at = Column(DateTime)
    return_reason = Column(Text)

    # Связи
    product = relationship("Product", back_populates="sales")
    agent = relationship("Agent", back_populates="sales")
    bonus = relationship("Bonus", uselist=False, back_populates="sale")

    def __repr__(self):
        return f"<Sale({self.product.name}, {self.agent.full_name}, {self.sale_date})>"


class BonusRule(Base):
    """Правила бонусов"""
    __tablename__ = 'bonus_rules'

    id = Column(Integer, primary_key=True)
    min_amount = Column(Float, nullable=False)
    max_amount = Column(Float, nullable=False)
    percent = Column(Float, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Связи
    bonuses = relationship("Bonus", back_populates="rule")

    def __repr__(self):
        return f"<BonusRule({self.min_amount}-{self.max_amount}: {self.percent}%)>"


class Bonus(Base):
    """Бонусы продавцов"""
    __tablename__ = 'bonuses'

    id = Column(Integer, primary_key=True)
    agent_id = Column(Integer, ForeignKey('agents.id'), nullable=False)
    sale_id = Column(Integer, ForeignKey('sales.id'), unique=True, nullable=False)
    rule_id = Column(Integer, ForeignKey('bonus_rules.id'), nullable=False)
    amount = Column(Float, nullable=False)
    percent_used = Column(Float, nullable=False)
    is_paid = Column(Boolean, default=False)
    paid_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Связи
    agent = relationship("Agent", back_populates="bonuses")
    sale = relationship("Sale", back_populates="bonus")
    rule = relationship("BonusRule", back_populates="bonuses")

    def __repr__(self):
        return f"<Bonus({self.agent.full_name}, {self.amount}, paid={self.is_paid})>"


class PriceHistory(Base):
    """История изменения цен"""
    __tablename__ = 'price_history'

    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey('products.id'), nullable=False)
    old_price = Column(Float)
    new_price = Column(Float, nullable=False)
    changed_by_id = Column(Integer, ForeignKey('agents.id'))
    changed_at = Column(DateTime, default=datetime.utcnow)

    # Связи
    product = relationship("Product", back_populates="price_history")
    changed_by = relationship("Agent")


class StockLog(Base):
    """Журнал движения товаров"""
    __tablename__ = 'stock_log'

    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey('products.id'), nullable=False)
    operation_type = Column(String(20), nullable=False)  # 'in', 'out', 'return'
    quantity = Column(Integer, nullable=False)
    warehouse = Column(String(100), nullable=False)
    reference_id = Column(Integer)  # ID связанной операции (sale_id, batch_id)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Связи
    product = relationship("Product", back_populates="stock_logs")

    __table_args__ = (
        CheckConstraint("operation_type IN ('in', 'out', 'return')", name='check_operation_type'),
    )


class ActionLog(Base):
    """Журнал всех действий в системе"""
    __tablename__ = 'action_log'

    id = Column(Integer, primary_key=True)
    agent_id = Column(Integer, ForeignKey('agents.id'))
    action_type = Column(String(50), nullable=False)
    entity_type = Column(String(50))  # 'batch', 'product', 'sale', etc.
    entity_id = Column(Integer)
    details = Column(Text)
    ip_address = Column(String(45))
    created_at = Column(DateTime, default=datetime.utcnow)

    # Связи
    agent = relationship("Agent")

    def __repr__(self):
        return f"<ActionLog({self.action_type}, {self.created_at})>"