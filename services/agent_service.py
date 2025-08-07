"""
Сервис для работы с агентами
"""
from sqlalchemy.orm import Session

from data.models import Agent


class AgentService:
    """Сервис для работы с агентами"""

    @staticmethod
    def get_or_create_agent(db: Session, telegram_id: int,
                           telegram_username: str = None,
                           full_name: str = None) -> Agent:
        """Получить или создать агента"""
        agent = db.query(Agent).filter_by(telegram_id=telegram_id).first()
        if not agent:
            agent = Agent(
                telegram_id=telegram_id,
                telegram_username=telegram_username or 'unknown',
                full_name=full_name or f'User {telegram_id}',
                is_admin=False
            )
            db.add(agent)
            db.commit()
        return agent
