"""
Модуль для работы с базой данных SQLite через SQLAlchemy
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.ext.declarative import declarative_base
from contextlib import contextmanager

from config import DATABASE_URL

# Создание движка БД
engine = create_engine(
    DATABASE_URL,
    connect_args={'check_same_thread': False},  # Для SQLite
    echo=False  # Поставьте True для отладки SQL-запросов
)

# Фабрика сессий
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Базовый класс для моделей
Base = declarative_base()


def init_db():
    """Инициализация базы данных - создание таблиц"""
    from data.models import (
        Agent, Batch, Product, Sale, BonusRule,
        Bonus, PriceHistory, StockLog, ActionLog
    )
    Base.metadata.create_all(bind=engine)

    # Создаем дефолтные бонусные правила если их нет
    with get_db() as db:
        if db.query(BonusRule).count() == 0:
            from config import DEFAULT_BONUS_RULES
            for rule in DEFAULT_BONUS_RULES:
                db_rule = BonusRule(
                    min_amount=rule['min_amount'],
                    max_amount=rule['max_amount'] if rule['max_amount'] != float('inf') else 999999999,
                    percent=rule['percent']
                )
                db.add(db_rule)
            db.commit()


@contextmanager
def get_db() -> Session:
    """Контекстный менеджер для работы с сессией БД"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_db_session() -> Session:
    """Получить сессию БД (для использования в асинхронных функциях)"""
    return SessionLocal()