"""User Service
============
Provides business logic for user-related operations such as registration,
authentication, profile updates, password changes, account soft deletion,
recovery, and user search.
"""

import uuid

from app.services.user.user_repository import UserRepository
from app.utils import security
from app.utils.models import User, UserCreate, UserRegister, UsersPublic, UserUpdate


class UserService:
    def __init__(self, repository: UserRepository):
        self.repository = repository

    def register_user(self, user_register: UserRegister) -> User:
        if self.repository.is_email_taken(user_register.email):
            raise ValueError("Email already registered")

        if self.repository.is_account_taken(user_register.account):
            raise ValueError("Account name already taken")

        user_create = UserCreate.model_validate(user_register)
        return self.repository.create_user(user_create)

    def get_user_by_id(self, user_id: uuid.UUID) -> User | None:
        return self.repository.get_user_by_id(user_id)

    def get_user_by_email(self, email: str) -> User | None:
        return self.repository.get_user_by_email(email)

    def get_user_by_account(self, account: str) -> User | None:
        return self.repository.get_user_by_account(account)

    def get_users_with_pagination(self, skip: int = 0, limit: int = 100) -> UsersPublic:
        users, count = self.repository.get_users(skip, limit)
        return UsersPublic(data=users, count=count)

    def update_user(self, user_id: uuid.UUID, user_update: UserUpdate) -> User:
        user = self.repository.get_user_by_id(user_id)
        if not user:
            raise ValueError("User not found")

        if user_update.email and self.repository.is_email_taken(
            user_update.email, exclude_user_id=user_id
        ):
            raise ValueError("Email already taken by another user")

        if user_update.account and self.repository.is_account_taken(
            user_update.account, exclude_user_id=user_id
        ):
            raise ValueError("Account name already taken by another user")

        return self.repository.update_user(user, user_update)

    def authenticate(self, email: str, password: str) -> User | None:
        return self.repository.authenticate(email, password)

    def is_email_available(
        self, email: str, exclude_user_id: uuid.UUID | None = None
    ) -> bool:
        return not self.repository.is_email_taken(email, exclude_user_id)

    def is_account_available(
        self, account: str, exclude_user_id: uuid.UUID | None = None
    ) -> bool:
        return not self.repository.is_account_taken(account, exclude_user_id)

    def update_password(
        self, user: User, current_password: str, new_password: str
    ) -> User:
        if not security.verify_password(current_password, user.password_hash):
            raise ValueError("Incorrect password")

        if current_password == new_password:
            raise ValueError("New password cannot be the same as the current one")

        password_hash = security.get_password_hash(new_password)
        return self.repository.update_user_password(user, password_hash)

    def search_users(self, query: str, skip: int = 0, limit: int = 20) -> UsersPublic:
        users, count = self.repository.search_users(query, skip, limit)
        return UsersPublic(data=users, count=count)

    def soft_delete_user(self, user_id: uuid.UUID) -> bool:
        user = self.repository.get_user_by_id(user_id)
        if not user:
            raise ValueError("User not found")

        if user.is_superuser:
            raise ValueError("Superuser accounts cannot be deleted")

        return self.repository.soft_delete_user(user_id)

    def recover_user(self, user_id: uuid.UUID) -> bool:
        return self.repository.recover_user(user_id)
