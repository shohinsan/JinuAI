"""SQLModel Schema Organization
==========================
This module contains all database models, schemas, and related types
organized by functional area for better maintainability.
"""

import uuid
from datetime import UTC, date, datetime
from enum import Enum
from typing import Annotated, Any, Dict, List, Optional

from fastapi import UploadFile
from pydantic import BaseModel, BeforeValidator, EmailStr, AliasChoices, field_validator
from sqlalchemy import Column, JSON
from sqlmodel import Field, Relationship, SQLModel

# ============================================================
# VALIDATORS & CUSTOM TYPES
# ============================================================


def lowercase_str(v: str | None) -> str | None:
    """Convert string to lowercase and strip whitespace."""
    if isinstance(v, str):
        return v.lower().strip()
    return v

# Custom type annotations
LowercaseStr = Annotated[str, BeforeValidator(lowercase_str)]
LowercaseEmailStr = Annotated[EmailStr, BeforeValidator(lowercase_str)]


# ============================================================
# ENUMS
# ============================================================


class UserRole(str, Enum):
    """User role enumeration."""

    USER = "user"
    ADMIN = "admin"

class ImageStatus(str, Enum):
    """Agent processing status enumeration."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class ImageStyle(str, Enum):
    """Predefined style presets"""
    POLAROID = "polaroid"
    FIGURE = "figure"
    FOODIE = "foodie"
    EXPLOSIVE = "explosive"
    CARD = "card"
    BUBBLEHEAD = "bubblehead"
    KEYCHAIN = "keychain"
    CYBERPANK = "cyberpank"
    GAMING = "gaming"
    AGING = "aging"
    BENCH = "bench"
    RESTORE = "restore"
    ISOMETRIC = "isometric"
    BURNING = "burning"
    ADS = "ads"
    GTA = "gta"
    REFLECTION = "reflection"


class ImageCategory(str, Enum):
    """Routing categories for refinement"""
    CREATIVITY = "creativity"
    TEMPLATE = "template"
    FIT = "fit"
    LIGHTBOX = "lightbox"
    


class ImageMimeType(str, Enum):
    """Supported output formats"""
    PNG = "image/png"
    JPEG = "image/jpeg"


class ImageAspectRatio(str, Enum):
    """Supported aspect ratios for image generation.
    
    Landscape: 21:9, 16:9, 4:3, 3:2
    Square: 1:1
    Portrait: 9:16, 3:4, 2:3
    Flexible: 5:4, 4:5
    """
    # Landscape
    ULTRAWIDE = "21:9"      # Ultra-wide cinematic
    WIDE = "16:9"           # Wide cinematic
    LANDSCAPE = "4:3"       # Classic landscape
    LANDSCAPE_3_2 = "3:2"   # Photo landscape
    
    # Square
    SQUARE = "1:1"          # Perfect square
    
    # Portrait
    TALL = "9:16"           # Stories/Reels
    PORTRAIT = "3:4"        # Classic portrait
    PORTRAIT_2_3 = "2:3"    # Photo portrait
    
    # Flexible
    FLEXIBLE_5_4 = "5:4"    # Slightly wider
    FLEXIBLE_4_5 = "4:5"    # Slightly taller


class AssetType(str, Enum):
    """Asset collection types matching MinIO structure"""
    MEDIA = "media"      # Generated AI images (output)
    MODEL = "model"      # Reference model photos
    STYLE = "style"      # Style templates (fit/template/product)


# ============================================================
# ASSET MODULE
# ============================================================


class Asset(SQLModel, table=True):
    """Tracks all images/assets stored in MinIO."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)

    # Storage location (internal use only - tags handle metadata)
    object_path: str = Field(max_length=500, index=True, unique=True)
    bucket_name: str = Field(default="jinuai-assets", max_length=100)

    # Classification
    asset_type: AssetType = Field(index=True)

    # Ownership & generation tracking
    user_id: uuid.UUID = Field(foreign_key="user.id", index=True)
    session_id: str | None = Field(default=None, max_length=100, index=True)

    # For media (generated images): track what was used to create it
    source_model_ids: list[uuid.UUID] | None = Field(default=None, sa_column=Column(JSON))
    source_style_id: uuid.UUID | None = Field(default=None, foreign_key="asset.id")
    prompt: str | None = Field(default=None, max_length=2000)

    # Status
    is_active: bool = Field(default=True, index=True)
    is_public: bool = Field(default=False)

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC), index=True)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    deleted_at: datetime | None = Field(default=None)

    # Relationships
    user: "User" = Relationship(back_populates="assets")


# ============================================================
# PHOTO MODULE
# ============================================================


class PhotoBase(SQLModel):
    """Base photo model with common fields."""

    small_uri: str | None = Field(default=None, max_length=500)
    medium_uri: str | None = Field(default=None, max_length=500)
    large_uri: str | None = Field(default=None, max_length=500)

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Photo(PhotoBase, table=True):
    """Photo table model."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)


# ============================================================
# USER MODULE
# ============================================================


class UserBase(SQLModel):
    """Base user model with common fields."""

    name: str = Field(min_length=8, max_length=40)
    email: EmailStr = Field(unique=True, index=True, max_length=255)
    account: str = Field(unique=True, max_length=32)
    roles: UserRole = Field(default=UserRole.USER)

    is_active: bool = True
    is_verified: bool = True
    is_superuser: bool = False

    bio: str | None = Field(default=None, max_length=200)
    dob: date | None = Field(default=None)
    phone: str | None = Field(default=None, max_length=20)

    avatar_photo_id: uuid.UUID | None = Field(default=None, foreign_key="photo.id")

    deleted_at: date | None = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class User(UserBase, table=True):
    """User table model."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    password_hash: str
    avatar_photo: Photo | None = Relationship(back_populates=None)

    # Relationships
    assets: list["Asset"] = Relationship(back_populates="user")


# User Schemas
class UserCreate(UserBase):
    """Schema for creating a new user."""

    password: str = Field(min_length=8, max_length=40)


class UserRegister(SQLModel):
    """Schema for user registration."""

    name: str = Field(min_length=8, max_length=40)
    email: LowercaseEmailStr = Field(max_length=255)
    account: LowercaseStr = Field(min_length=6, max_length=32)
    bio: str | None = Field(default=None, max_length=1000)
    dob: date | None = Field(default=None)
    phone: str | None = Field(default=None, max_length=20)
    password: str = Field(min_length=8, max_length=40)


class UserUpdate(UserBase):
    """Schema for updating user information."""

    email: LowercaseEmailStr = Field(default=None, max_length=255)  # type: ignore
    account: LowercaseStr = Field(default=None, min_length=6, max_length=32)  # type: ignore
    password: str = Field(default=None, min_length=8, max_length=40)


class UpdatePassword(SQLModel):
    """Schema for updating user password."""

    current_password: str = Field(min_length=8, max_length=40)
    new_password: str = Field(min_length=8, max_length=40)


class UserPublic(UserBase):
    """Public user schema (excludes sensitive information)."""

    id: uuid.UUID


class UsersPublic(SQLModel):
    """Schema for paginated user list."""

    data: list[UserPublic]
    count: int










# ============================================================
# AUTHENTICATION MODULE
# ============================================================


class Message(SQLModel):
    """Generic message schema."""

    message: str


class Token(SQLModel):
    """JSON payload containing access token."""

    access_token: str
    token_type: str = "bearer"


class TokenWithRefresh(SQLModel):
    """JSON payload containing both access and refresh tokens."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshTokenRequest(SQLModel):
    """Refresh token request schema."""

    refresh_token: str


class TokenPayload(SQLModel):
    """Contents of JWT token."""

    sub: str | None = None


class NewPassword(SQLModel):
    """Schema for password reset."""

    token: str
    new_password: str = Field(min_length=8, max_length=40)


class EmailPasswordLogin(SQLModel):
    """Schema for email/password login."""

    email: str
    password: str




# ===========================================================
# DO NOT TOUCH THIS CODE, I PUT THIS HERE TO WORK ON LATER
# ============================================================


class ImageRequest(BaseModel):
    """Request model for image generation.

    Expect 1–3 uploaded images in the `files` field. When the frontend is in
    a `fit` flow, include the selected model/style image as the first file,
    followed by up to two optional user-uploaded images. All files must be PNG
    or JPEG.
    """
    prompt: Optional[str] = Field(default=None, description="User prompt for image generation")
    files: List[UploadFile] = Field(..., description="1–3 input image files (png/jpg)")
    style: Optional[str] = Field(default=None, description="Optional style preset key (matches ImageStyle values)")
    aspect_ratio: Optional[ImageAspectRatio] = Field(default=None, description="Aspect ratio of the generated images. Supported values are '1:1', '3:4', '4:3', '9:16', and '16:9'")
    session_id: Optional[str] = Field(default=None, description="Session identifier to persist state")
    category: Optional[ImageCategory] = Field(None, description="Routing category: 'creativity', 'template', 'fit', or 'lightbox'")


@field_validator("files")
@classmethod
def validate_files(cls, value: List[UploadFile]) -> List[UploadFile]:
    """Ensure 1-3 files are provided and are of correct type."""
    if not (1 <= len(value) <= 3):
        raise ValueError("You must upload between 1 and 3 image files.")

    allowed_types = {"image/png", "image/jpeg"}
    for file in value:
        if file.content_type not in allowed_types:
            raise ValueError(f"Unsupported file type: {file.content_type}. Only PNG and JPEG are allowed.")
    return value

@field_validator("aspect_ratio", mode="before")
@classmethod
def normalize_aspect_ratio(cls, value: Any) -> Any:
    """Map friendly names or ratio strings to the expected enum values."""
    if value is None or isinstance(value, ImageAspectRatio):
        return value

    str_value = str(value).strip().lower()
    
    # Alias map for friendly names
    alias_map = {
        # Landscape
        "ultrawide": ImageAspectRatio.ULTRAWIDE,
        "wide": ImageAspectRatio.WIDE,
        "landscape": ImageAspectRatio.LANDSCAPE,
        
        # Square
        "square": ImageAspectRatio.SQUARE,
        
        # Portrait
        "tall": ImageAspectRatio.TALL,
        "portrait": ImageAspectRatio.PORTRAIT,
    }

    if str_value in alias_map:
        return alias_map[str_value]
    
    # Also allow direct ratio values like "16:9", "3:2", etc.
    ratio_map = {
        "21:9": ImageAspectRatio.ULTRAWIDE,
        "16:9": ImageAspectRatio.WIDE,
        "4:3": ImageAspectRatio.LANDSCAPE,
        "3:2": ImageAspectRatio.LANDSCAPE_3_2,
        "1:1": ImageAspectRatio.SQUARE,
        "9:16": ImageAspectRatio.TALL,
        "3:4": ImageAspectRatio.PORTRAIT,
        "2:3": ImageAspectRatio.PORTRAIT_2_3,
        "5:4": ImageAspectRatio.FLEXIBLE_5_4,
        "4:5": ImageAspectRatio.FLEXIBLE_4_5,
    }
    
    if str_value in ratio_map:
        return ratio_map[str_value]

    return value

@field_validator("style", mode="before")
@classmethod
def normalize_style(cls, value: Any) -> Any:
    """Allow enum entries or raw strings for styles."""
    if value is None or isinstance(value, ImageStyle):
        return value

    str_value = str(value).strip().lower()
   
    # Map common aliases to ImageStyle enum values
    alias_map = {style.value: style for style in ImageStyle}

    if str_value in alias_map:
        return alias_map[str_value]

    return value

class ImageResponse(BaseModel):
    """Response model for image generation"""
    status: ImageStatus
    prompt: Optional[str] = None
    style: str | None = None
    aspect_ratio: str | None = None
    session_id: str
    category: str | None = None
    user_id: str
    output_file: Optional[str] = None
    media_object_path: Optional[str] = None
