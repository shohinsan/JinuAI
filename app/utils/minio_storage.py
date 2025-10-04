import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO

from minio import Minio
from minio.error import S3Error

from app.utils.config import settings

logger = logging.getLogger(__name__)

_STRUCTURE_LOCK = asyncio.Lock()
_STATE = {"initialized": False}

_STYLE_FOLDERS = {"fit", "template", "product"}


@dataclass(slots=True)
class UserMediaObject:
    """Metadata for an object stored in MinIO-backed collections."""

    object_path: str
    filename: str
    size: int | None
    last_modified: datetime | None
    collection: str | None = None
    style: str | None = None


def _get_minio_client() -> Minio | None:
    return settings.minio_client


async def ensure_minio_structure() -> None:
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
            except S3Error:  # pragma: no cover - network/storage failure path
                logger.exception("Failed to verify MinIO bucket %s", bucket)
                raise

            placeholders: list[str] = []

            model_prefix = settings.MINIO_PREFIX_MODELS.rstrip('/')
            if model_prefix:
                placeholders.append(f"{model_prefix}/.keep")
                placeholders.append(f"{model_prefix}/static/.keep")
            else:
                placeholders.append('.keep')

            style_prefix = settings.MINIO_PREFIX_STYLES.rstrip('/')
            if style_prefix:
                placeholders.append(f"{style_prefix}/.keep")
                placeholders.extend(
                    [f"{style_prefix}/{folder}/.keep" for folder in _STYLE_FOLDERS]
                )

            media_prefix = settings.MINIO_PREFIX_MEDIA.rstrip('/')
            if media_prefix:
                placeholders.append(f"{media_prefix}/.keep")

            for object_name in placeholders:
                try:
                    client.stat_object(bucket, object_name)
                    continue
                except S3Error as exc:
                    if exc.code not in {"NoSuchKey", "NoSuchObject", "NoSuchEntity"}:
                        logger.debug(
                            "Skipping placeholder creation for %s due to unexpected error: %s",
                            object_name,
                            exc,
                        )
                        continue

                try:
                    data = BytesIO(b"")
                    client.put_object(
                        bucket,
                        object_name,
                        data,
                        length=0,
                        content_type="application/octet-stream",
                    )
                except S3Error as exc:
                    logger.debug(
                        "Unable to create placeholder %s in bucket %s: %s",
                        object_name,
                        bucket,
                        exc,
                    )

        await asyncio.to_thread(_setup)
        _STATE["initialized"] = True


async def _upload_object(
    object_name: str,
    data: bytes,
    *,
    content_type: str | None = None,
) -> str | None:
    client = _get_minio_client()
    if client is None:
        return None

    await ensure_minio_structure()

    bucket = settings.MINIO_BUCKET_NAME

    def _put() -> str:
        stream = BytesIO(data)
        return_object_name = object_name
        client.put_object(
            bucket,
            return_object_name,
            stream,
            length=len(data),
            content_type=content_type,
        )
        return return_object_name

    try:
        return await asyncio.to_thread(_put)
    except S3Error:  # pragma: no cover - network/storage failure path
        logger.exception("Failed to upload object %s to MinIO", object_name)
    return None


async def upload_user_media(
    *,
    user_id: str,
    filename: str,
    data: bytes,
    content_type: str | None = None,
) -> str | None:
    prefix = settings.MINIO_PREFIX_MEDIA.rstrip("/")
    object_name = f"{prefix}/{user_id}/{filename}"
    return await _upload_object(object_name, data, content_type=content_type)


async def list_user_media_objects(user_id: str) -> list[UserMediaObject]:
    """List media objects stored for a specific user.

    Returns an empty list when MinIO is not configured.
    """
    client = _get_minio_client()
    if client is None:
        return []

    await ensure_minio_structure()

    bucket = settings.MINIO_BUCKET_NAME
    prefix = settings.MINIO_PREFIX_MEDIA.rstrip("/")
    object_prefix = f"{prefix}/{user_id}/"

    def _list() -> list[UserMediaObject]:
        results: list[UserMediaObject] = []
        try:
            for obj in client.list_objects(
                bucket,
                prefix=object_prefix,
                recursive=False,
            ):
                if getattr(obj, "is_dir", False):
                    continue
                object_name = obj.object_name
                filename = object_name.rsplit("/", 1)[-1]
                size = getattr(obj, "size", None)
                last_modified = getattr(obj, "last_modified", None)
                results.append(
                    UserMediaObject(
                        object_path=object_name,
                        filename=filename,
                        size=size,
                        last_modified=last_modified,
                        collection="media",
                    )
                )
        except S3Error:  # pragma: no cover - network/storage failure path
            logger.exception("Failed to list user media objects for %s", user_id)
        return results

    return await asyncio.to_thread(_list)


async def list_model_assets() -> list[UserMediaObject]:
    """List globally available model assets stored in MinIO."""
    client = _get_minio_client()
    if client is None:
        return []

    await ensure_minio_structure()

    bucket = settings.MINIO_BUCKET_NAME
    prefix = settings.MINIO_PREFIX_MODELS.rstrip('/')
    list_prefix = f"{prefix}/" if prefix else ''

    def _list() -> list[UserMediaObject]:
        results: list[UserMediaObject] = []
        try:
            for obj in client.list_objects(
                bucket,
                prefix=list_prefix,
                recursive=True,
            ):
                if getattr(obj, 'is_dir', False):
                    continue

                object_name = obj.object_name
                filename = object_name.rsplit('/', 1)[-1]
                if filename == '.keep':
                    continue

                results.append(
                    UserMediaObject(
                        object_path=object_name,
                        filename=filename,
                        size=getattr(obj, 'size', None),
                        last_modified=getattr(obj, 'last_modified', None),
                        collection='models',
                    )
                )
        except S3Error:  # pragma: no cover - network/storage failure path
            logger.exception('Failed to list model assets from MinIO')
        return results

    return await asyncio.to_thread(_list)


async def list_style_assets(style: str | None = None) -> list[UserMediaObject]:
    """List style assets, optionally filtered by style folder."""
    client = _get_minio_client()
    if client is None:
        return []

    await ensure_minio_structure()

    bucket = settings.MINIO_BUCKET_NAME
    base_prefix = settings.MINIO_PREFIX_STYLES.rstrip('/')
    list_prefix = f"{base_prefix}/" if base_prefix else ''
    normalized_filter = style.lower() if style else None

    def _list() -> list[UserMediaObject]:
        results: list[UserMediaObject] = []
        try:
            for obj in client.list_objects(
                bucket,
                prefix=list_prefix,
                recursive=True,
            ):
                if getattr(obj, 'is_dir', False):
                    continue

                object_name = obj.object_name
                filename = object_name.rsplit('/', 1)[-1]
                if filename == '.keep':
                    continue

                path_parts = object_name.split('/')
                inferred_style = path_parts[-2] if len(path_parts) >= 3 else None
                if normalized_filter and inferred_style != normalized_filter:
                    continue

                results.append(
                    UserMediaObject(
                        object_path=object_name,
                        filename=filename,
                        size=getattr(obj, 'size', None),
                        last_modified=getattr(obj, 'last_modified', None),
                        collection='styles',
                        style=inferred_style,
                    )
                )
        except S3Error:  # pragma: no cover - network/storage failure path
            logger.exception('Failed to list style assets from MinIO')
        return results

    return await asyncio.to_thread(_list)




async def fetch_object_by_path(object_path: str) -> bytes | None:
    """Fetch a MinIO object by its object path."""
    client = _get_minio_client()
    if client is None:
        return None

    await ensure_minio_structure()

    bucket = settings.MINIO_BUCKET_NAME

    def _get() -> bytes | None:
        try:
            response = client.get_object(bucket, object_path)
        except S3Error as exc:  # pragma: no cover - network/storage failure path
            if exc.code not in {"NoSuchKey", "NoSuchObject", "NoSuchEntity"}:
                logger.exception("Failed to fetch object %s from MinIO", object_path)
            return None

        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    return await asyncio.to_thread(_get)




async def fetch_user_media_object(
    *,
    user_id: str,
    filename: str,
) -> bytes | None:
    """Fetch raw bytes for a stored media object.

    Returns ``None`` when MinIO is unavailable or the object does not exist.
    """
    client = _get_minio_client()
    if client is None:
        return None

    await ensure_minio_structure()

    bucket = settings.MINIO_BUCKET_NAME
    prefix = settings.MINIO_PREFIX_MEDIA.rstrip("/")
    object_name = f"{prefix}/{user_id}/{filename}"

    def _get() -> bytes | None:
        try:
            response = client.get_object(bucket, object_name)
        except S3Error as exc:  # pragma: no cover - network/storage failure path
            if exc.code not in {"NoSuchKey", "NoSuchObject", "NoSuchEntity"}:
                logger.exception(
                    "Failed to fetch media object %s for user %s", filename, user_id
                )
            return None

        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    return await asyncio.to_thread(_get)


async def upload_model_asset(
    *,
    filename: str,
    data: bytes,
    content_type: str | None = None,
) -> str | None:
    prefix = settings.MINIO_PREFIX_MODELS.rstrip("/")
    object_name = f"{prefix}/static/{filename}" if prefix else f"static/{filename}"
    return await _upload_object(object_name, data, content_type=content_type)


async def upload_style_asset(
    *,
    style: str,
    filename: str,
    data: bytes,
    content_type: str | None = None,
) -> str | None:
    normalized_style = style.lower()
    if normalized_style not in _STYLE_FOLDERS:
        raise ValueError(f"Unsupported style folder '{style}'. Expected one of {_STYLE_FOLDERS}.")

    prefix = settings.MINIO_PREFIX_STYLES.rstrip("/")
    object_name = f"{prefix}/{normalized_style}/{filename}"
    return await _upload_object(object_name, data, content_type=content_type)
