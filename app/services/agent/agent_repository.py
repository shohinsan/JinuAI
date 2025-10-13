"""Agent Repository
=================
Handles all agent and asset-related database operations.
"""

import uuid
from datetime import UTC, datetime

from sqlmodel import Session, select, or_

from app.utils.models import Asset, AssetType


class AgentRepository:
    """Repository for Agent and Asset database operations."""

    def __init__(self, session: Session):
        self.session = session

    # ===== Asset Methods =====

    def create_asset(
        self,
        *,
        asset_id: uuid.UUID | None = None,
        object_path: str,
        bucket_name: str,
        filename: str,
        asset_type: AssetType,
        user_id: uuid.UUID,
        session_id: str | None = None,
        source_model_ids: list[uuid.UUID] | None = None,
        source_style_id: uuid.UUID | None = None,
        prompt: str | None = None,
    ) -> Asset:
        """Create a new asset record in the database."""
        asset = Asset(
            id=asset_id or uuid.uuid4(),
            object_path=object_path,
            bucket_name=bucket_name,
            asset_type=asset_type,
            user_id=user_id,
            session_id=session_id,
            source_model_ids=source_model_ids,
            source_style_id=source_style_id,
            prompt=prompt,
        )
        self.session.add(asset)
        self.session.commit()
        self.session.refresh(asset)
        return asset

    def get_asset_by_id(self, asset_id: uuid.UUID) -> Asset | None:
        """Retrieve an asset by its ID."""
        return self.session.get(Asset, asset_id)

    def get_asset_by_path(self, object_path: str) -> Asset | None:
        """Retrieve an asset by its object path."""
        statement = select(Asset).where(Asset.object_path == object_path)
        return self.session.exec(statement).first()

    def list_user_assets(
        self,
        user_id: uuid.UUID,
        asset_type: AssetType | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Asset]:
        """List assets for a specific user, optionally filtered by type."""
        statement = (
            select(Asset)
            .where(Asset.user_id == user_id, Asset.is_active == True)
            .order_by(Asset.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if asset_type:
            statement = statement.where(Asset.asset_type == asset_type)
        return list(self.session.exec(statement).all())

    def list_assets_by_session(
        self, session_id: str, user_id: uuid.UUID | None = None
    ) -> list[Asset]:
        """List all assets associated with a specific session."""
        statement = select(Asset).where(
            Asset.session_id == session_id, Asset.is_active == True
        )
        if user_id:
            statement = statement.where(Asset.user_id == user_id)
        statement = statement.order_by(Asset.created_at.desc())
        return list(self.session.exec(statement).all())

    def list_style_assets(
        self,
        *,
        style_subcategory: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Asset]:
        """List style assets, optionally filtered by subcategory."""
        statement = (
            select(Asset)
            .where(Asset.asset_type == AssetType.STYLE, Asset.is_active == True)
            .order_by(Asset.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if style_subcategory:
            statement = statement.where(Asset.style_subcategory == style_subcategory)
        return list(self.session.exec(statement).all())

    def list_model_assets(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        user_id: uuid.UUID | None = None,
    ) -> list[Asset]:
        """List model reference assets."""
        statement = (
            select(Asset)
            .where(Asset.asset_type == AssetType.MODEL, Asset.is_active == True)
            .order_by(Asset.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if user_id:
            statement = statement.where(Asset.user_id == user_id)
        return list(self.session.exec(statement).all())

    def soft_delete_asset(self, asset_id: uuid.UUID) -> Asset | None:
        """Soft delete an asset by marking it as inactive."""
        asset = self.get_asset_by_id(asset_id)
        if not asset:
            return None
        asset.is_active = False
        asset.deleted_at = datetime.now(UTC)
        self.session.add(asset)
        self.session.commit()
        self.session.refresh(asset)
        return asset

    def update_asset_visibility(
        self, asset_id: uuid.UUID, is_public: bool
    ) -> Asset | None:
        """Update the public visibility of an asset."""
        asset = self.get_asset_by_id(asset_id)
        if not asset:
            return None
        asset.is_public = is_public
        asset.updated_at = datetime.now(UTC)
        self.session.add(asset)
        self.session.commit()
        self.session.refresh(asset)
        return asset

    def resolve_asset_by_identifier(
        self, identifier: str, user_id: uuid.UUID
    ) -> Asset | None:
        """Resolve an asset for a user by UUID, filename, or object path.

        Supports flexible matching:
        - Direct UUID match
        - Exact filename or object_path match
        - Partial filename match (with extension guessing)
        - Partial path match
        """
        from sqlalchemy import or_

        normalized = identifier.strip()

        # Try UUID first
        try:
            asset_uuid = uuid.UUID(normalized)
            asset = self.get_asset_by_id(asset_uuid)
            if asset and asset.user_id == user_id and asset.is_active:
                return asset
            return None
        except ValueError:
            pass

        # Build filename/path conditions
        base_conditions = [
            Asset.object_path == normalized,
            Asset.filename == normalized,
        ]

        if "." not in normalized:
            # If no extension, try fuzzy matching
            base_conditions.append(Asset.filename.like(f"{normalized}.%"))
            base_conditions.append(Asset.object_path.like(f"%/{normalized}.%"))
        else:
            base_conditions.append(Asset.object_path.like(f"%/{normalized}"))

        statement = (
            select(Asset)
            .where(
                Asset.user_id == user_id,
                Asset.is_active == True,
                or_(*base_conditions),
            )
            .order_by(Asset.created_at.desc())
        )

        return self.session.exec(statement).first()

    def search_assets_by_prompt(
        self, user_id: uuid.UUID, search_query: str, limit: int = 20
    ) -> list[Asset]:
        """Search user's media assets by prompt text."""
        statement = (
            select(Asset)
            .where(
                Asset.user_id == user_id,
                Asset.asset_type == AssetType.MEDIA,
                Asset.is_active == True,  # noqa: E712
                Asset.prompt.ilike(f"%{search_query}%"),  # type: ignore
            )
            .order_by(Asset.created_at.desc())  # type: ignore
            .limit(limit)
        )
        return list(self.session.exec(statement).all())
