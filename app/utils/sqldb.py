"""Database Initialization
=======================
Creates the database engine and initializes the first superuser
in the database if not already present.
"""

from sqlmodel import Session, create_engine

from app.services.user.user_repository import UserRepository
from app.utils.config import settings
from app.utils.models import UserCreate

engine = create_engine(str(settings.SYNC_DATABASE_URI))


def init_db(session: Session) -> None:
    repository = UserRepository(session)
    user = repository.get_user_by_email(settings.FIRST_SUPERUSER)
    if not user:
        user_in = UserCreate(
            email=settings.FIRST_SUPERUSER,
            password=settings.FIRST_SUPERUSER_PASSWORD,
            account=settings.FIRST_SUPERUSER_ACCOUNT,
            name=settings.FIRST_SUPERUSER_NAME,
            is_superuser=True,
        )
        user = repository.create_user(user_in)