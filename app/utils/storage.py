"""MinIO Storage Integration
========================
Handles all MinIO object storage operations for the application.
Uses object tagging for organization instead of folder hierarchies.

Tagging Strategy:
- collection: media|models|styles
- type: static|custom (for models)
- style: fit|template|product|styles:*|lightbox:* (for styles)
- user_id: UUID (for media)
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO

from minio import Minio
from minio.commonconfig import Tags
from minio.error import S3Error

from app.utils.config import settings

logger = logging.getLogger(__name__)

_STRUCTURE_LOCK = asyncio.Lock()
_STATE = {"initialized": False}


@dataclass(slots=True)
class UserMediaObject:
    """Metadata for an object stored in MinIO-backed collections."""

    object_path: str
    filename: str
    size: int | None
    last_modified: datetime | None
    collection: str | None = None
    style: str | None = None
    tags: dict[str, str] | None = None


def _get_minio_client() -> Minio | None:
    """Get configured MinIO client or None if disabled."""
    return settings.minio_client


async def ensure_minio_structure() -> None:
    """Ensure the MinIO bucket exists.
    With tagging strategy, we use a flat structure in the bucket.
    """
    client = _get_minio_client()
    if client is None:
        return

    if _STATE["initialized"]:
        return

    async with _STRUCTURE_LOCK:
        if _STATE["initialized"]:
            return

        bucket = settings.MINIO_BUCKET_NAME

        def _setup() -> None:
            try:
                if not client.bucket_exists(bucket):
                    client.make_bucket(bucket)
                    logger.info("Created MinIO bucket: %s", bucket)
            except S3Error:
                logger.exception("Failed to verify MinIO bucket %s", bucket)
                raise

        await asyncio.to_thread(_setup)
        _STATE["initialized"] = True
        logger.info("MinIO structure initialized")


async def upload_user_media(
    user_id: str,
    filename: str,
    data: bytes,
    content_type: str = "image/png",
) -> str | None:
    """Upload a user media file (generated image) to MinIO.
    Stores in flat structure: media/{filename}
    Tags: collection=media, user_id={user_id}

    Args:
        user_id: User ID
        filename: Filename to store
        data: File bytes
        content_type: MIME type

    Returns:
        Object path if successful, None if MinIO is disabled or fails
    """
    client = _get_minio_client()
    if client is None:
        logger.debug("MinIO disabled, skipping upload for %s", filename)
        return None

    await ensure_minio_structure()

    bucket = settings.MINIO_BUCKET_NAME
    prefix = settings.MINIO_PREFIX_MEDIA.rstrip("/")
    object_name = f"{prefix}/{filename}" if prefix else filename

    def _upload() -> str:
        try:
            # Upload object
            client.put_object(
                bucket,
                object_name,
                BytesIO(data),
                length=len(data),
                content_type=content_type,
            )

            # Set tags
            tags = Tags(for_object=True)
            tags["collection"] = "media"
            tags["user_id"] = user_id
            client.set_object_tags(bucket, object_name, tags)

            logger.info("Uploaded media: %s with tags", object_name)
            return object_name
        except S3Error:
            logger.exception("Failed to upload media %s", object_name)
            return ""

    result = await asyncio.to_thread(_upload)
    return result if result else None


async def upload_model_asset(
    filename: str,
    data: bytes,
    content_type: str = "image/png",
    is_static: bool = True,
) -> str | None:
    """Upload a model reference asset to MinIO.
    Stores in flat structure: models/{filename}
    Tags: collection=models, type=static|custom

    Args:
        filename: Filename to store
        data: File bytes
        content_type: MIME type
        is_static: True for static models, False for user-uploaded custom models

    Returns:
        Object path if successful, None if disabled or fails
    """
    client = _get_minio_client()
    if client is None:
        return None

    await ensure_minio_structure()

    bucket = settings.MINIO_BUCKET_NAME
    prefix = settings.MINIO_PREFIX_MODELS.rstrip("/")
    object_name = f"{prefix}/{filename}" if prefix else filename

    def _upload() -> str:
        try:
            # Upload object
            client.put_object(
                bucket,
                object_name,
                BytesIO(data),
                length=len(data),
                content_type=content_type,
            )

            # Set tags
            tags = Tags(for_object=True)
            tags["collection"] = "models"
            tags["type"] = "static" if is_static else "custom"
            client.set_object_tags(bucket, object_name, tags)

            logger.info("Uploaded model: %s with tags", object_name)
            return object_name
        except S3Error:
            logger.exception("Failed to upload model %s", object_name)
            return ""

    result = await asyncio.to_thread(_upload)
    return result if result else None


async def upload_style_asset(
    style: str,
    filename: str,
    data: bytes,
    content_type: str = "image/png",
) -> str | None:
    """Upload a style template asset to MinIO.
    Stores in flat structure: styles/{filename}
    Tags: collection=styles, style={fit|template|product|styles:*|lightbox:*}

    Args:
        style: Style subcategory (fit, template, product, or namespaced template groups like styles:* / lightbox:*)
        filename: Filename to store
        data: File bytes
        content_type: MIME type

    Returns:
        Object path if successful, None if disabled or fails
    """
    client = _get_minio_client()
    if client is None:
        return None

    await ensure_minio_structure()

    bucket = settings.MINIO_BUCKET_NAME
    prefix = settings.MINIO_PREFIX_STYLES.rstrip("/")
    object_name = f"{prefix}/{filename}" if prefix else filename

    def _upload() -> str:
        try:
            # Upload object
            client.put_object(
                bucket,
                object_name,
                BytesIO(data),
                length=len(data),
                content_type=content_type,
            )

            # Set tags
            tags = Tags(for_object=True)
            tags["collection"] = "styles"
            tags["style"] = style.lower()
            client.set_object_tags(bucket, object_name, tags)

            logger.info("Uploaded style: %s with tags", object_name)
            return object_name
        except S3Error:
            logger.exception("Failed to upload style %s", object_name)
            return ""

    result = await asyncio.to_thread(_upload)
    return result if result else None


async def fetch_object_by_path(object_path: str) -> bytes | None:
    """Retrieve an object from MinIO by its path.

    Args:
        object_path: Full object path in bucket

    Returns:
        File bytes if found, None otherwise
    """
    client = _get_minio_client()
    if client is None:
        return None

    bucket = settings.MINIO_BUCKET_NAME

    def _fetch() -> bytes | None:
        try:
            response = client.get_object(bucket, object_path)
            data = response.read()
            response.close()
            response.release_conn()
            return data
        except S3Error as exc:
            if exc.code in {"NoSuchKey", "NoSuchObject"}:
                logger.debug("Object not found: %s", object_path)
            else:
                logger.exception("Failed to fetch object %s", object_path)
            return None

    return await asyncio.to_thread(_fetch)


async def list_user_media_objects(user_id: str) -> list[UserMediaObject]:
    """List all media objects for a specific user using tag filtering.

    Args:
        user_id: User ID

    Returns:
        List of user media objects
    """
    client = _get_minio_client()
    if client is None:
        return []

    bucket = settings.MINIO_BUCKET_NAME
    prefix = settings.MINIO_PREFIX_MEDIA.rstrip("/") if settings.MINIO_PREFIX_MEDIA else ""

    def _list() -> list[UserMediaObject]:
        try:
            # List all objects in media prefix
            list_prefix = f"{prefix}/" if prefix else ""
            objects = client.list_objects(bucket, prefix=list_prefix, recursive=True)
            result = []

            for obj in objects:
                # Get object tags to filter by user_id
                try:
                    tags = client.get_object_tags(bucket, obj.object_name)
                    tag_dict = tags if isinstance(tags, dict) else {}

                    # Only include if it's media collection for this user
                    if tag_dict.get("collection") != "media":
                        continue
                    if tag_dict.get("user_id") != user_id:
                        continue

                    filename = obj.object_name.split("/")[-1]
                    result.append(
                        UserMediaObject(
                            object_path=obj.object_name,
                            filename=filename,
                            size=obj.size,
                            last_modified=obj.last_modified,
                            collection="media",
                            tags=tag_dict,
                        )
                    )
                except S3Error:
                    # If tags can't be retrieved, skip this object
                    logger.debug("Could not get tags for %s", obj.object_name)
                    continue

            return result
        except S3Error:
            logger.exception("Failed to list user media for %s", user_id)
            return []

    return await asyncio.to_thread(_list)



async def list_model_assets() -> list[UserMediaObject]:
    """List all model reference assets using tag filtering.

    Returns:
        List of model assets
    """
    client = _get_minio_client()
    if client is None:
        return []

    bucket = settings.MINIO_BUCKET_NAME
    prefix = settings.MINIO_PREFIX_MODELS.rstrip("/") if settings.MINIO_PREFIX_MODELS else ""

    def _list() -> list[UserMediaObject]:
        try:
            # List all objects in models prefix
            list_prefix = f"{prefix}/" if prefix else ""
            objects = client.list_objects(bucket, prefix=list_prefix, recursive=True)
            result = []

            for obj in objects:
                # Get object tags to determine collection
                try:
                    tags = client.get_object_tags(bucket, obj.object_name)
                    tag_dict = tags if isinstance(tags, dict) else {}

                    # Only include if it's models collection
                    if tag_dict.get("collection") != "models":
                        continue

                    filename = obj.object_name.split("/")[-1]
                    result.append(
                        UserMediaObject(
                            object_path=obj.object_name,
                            filename=filename,
                            size=obj.size,
                            last_modified=obj.last_modified,
                            collection="models",
                            tags=tag_dict,
                        )
                    )
                except S3Error:
                    # If tags can't be retrieved, skip this object
                    logger.debug("Could not get tags for %s", obj.object_name)
                    continue

            return result
        except S3Error:
            logger.exception("Failed to list model assets")
            return []

    return await asyncio.to_thread(_list)


async def list_style_assets(style: str | None = None) -> list[UserMediaObject]:
    """List style template assets, optionally filtered by subcategory using tags.

    Args:
        style: Optional style subcategory to filter (fit, template, product, or namespaced keys like styles:* / lightbox:*)

    Returns:
        List of style assets
    """
    client = _get_minio_client()
    if client is None:
        return []

    bucket = settings.MINIO_BUCKET_NAME
    prefix = settings.MINIO_PREFIX_STYLES.rstrip("/") if settings.MINIO_PREFIX_STYLES else ""

    def _list() -> list[UserMediaObject]:
        try:
            # List all objects in styles prefix
            list_prefix = f"{prefix}/" if prefix else ""
            objects = client.list_objects(bucket, prefix=list_prefix, recursive=True)
            result = []

            for obj in objects:
                # Get object tags to determine collection and style
                try:
                    tags = client.get_object_tags(bucket, obj.object_name)
                    tag_dict = tags if isinstance(tags, dict) else {}

                    # Only include if it's a styles collection
                    if tag_dict.get("collection") != "styles":
                        continue

                    # Filter by style if specified
                    obj_style = tag_dict.get("style")
                    if style and obj_style != style.lower():
                        continue

                    filename = obj.object_name.split("/")[-1]
                    result.append(
                        UserMediaObject(
                            object_path=obj.object_name,
                            filename=filename,
                            size=obj.size,
                            last_modified=obj.last_modified,
                            collection="styles",
                            style=obj_style,
                            tags=tag_dict,
                        )
                    )
                except S3Error:
                    # If tags can't be retrieved, skip this object
                    logger.debug("Could not get tags for %s", obj.object_name)
                    continue

            return result
        except S3Error:
            logger.exception("Failed to list style assets")
            return []

    return await asyncio.to_thread(_list)


async def fetch_user_media_object(user_id: str, filename: str) -> bytes | None:
    """Fetch a specific media object for a user.

    Args:
        user_id: User ID
        filename: Filename to retrieve

    Returns:
        File bytes if found, None otherwise
    """
    prefix = settings.MINIO_PREFIX_MEDIA.rstrip("/")
    object_path = f"{prefix}/{user_id}/{filename}" if prefix else f"{user_id}/{filename}"
    return await fetch_object_by_path(object_path)


async def delete_object(object_path: str) -> bool:
    """Delete an object from MinIO.

    Args:
        object_path: Full object path to delete

    Returns:
        True if successful, False otherwise
    """
    client = _get_minio_client()
    if client is None:
        return False

    bucket = settings.MINIO_BUCKET_NAME

    def _delete() -> bool:
        try:
            client.remove_object(bucket, object_path)
            logger.info("Deleted object: %s", object_path)
            return True
        except S3Error:
            logger.exception("Failed to delete object %s", object_path)
            return False

    return await asyncio.to_thread(_delete)
