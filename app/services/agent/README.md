# Agent Services Architecture

## Overview

This module implements a clean **service-oriented architecture** for AI agent operations, asset management, and image generation workflows. The design follows separation of concerns with clear boundaries between routes, services, repositories, and utilities.

---

## Architecture Layers

```
┌──────────────────────────────────────────────────────────┐
│                    Routes (Presentation)                  │
│                  app/routes/agent.py                      │
│  • HTTP request/response handling                         │
│  • Input validation                                       │
│  • Dependency injection                                   │
└──────────────────────────────────────────────────────────┘
                            ↓
┌──────────────────────────────────────────────────────────┐
│                  Services (Business Logic)                │
│          app/services/agent/                              │
│  ┌────────────────────┐    ┌──────────────────────┐      │
│  │   AgentService     │───▶│   AssetService       │      │
│  │  • Image generation│    │  • Upload & track    │      │
│  │  • Workflow        │    │  • Asset retrieval   │      │
│  │    orchestration   │    │  • Visibility mgmt   │      │
│  └────────────────────┘    └──────────────────────┘      │
└──────────────────────────────────────────────────────────┘
                            ↓
┌──────────────────────────────────────────────────────────┐
│               Repository (Data Access)                    │
│     app/services/agent/asset_repository.py                │
│  • Database CRUD operations                               │
│  • Query composition                                      │
│  • Transaction management                                 │
└──────────────────────────────────────────────────────────┘
                            ↓
┌──────────────────────────────────────────────────────────┐
│              Storage & External Services                  │
│  • MinIO (object storage)                                 │
│  • Google Gemini (image generation)                       │
│  • PostgreSQL (metadata)                                  │
└──────────────────────────────────────────────────────────┘
```

---

## Components

### 1. **AssetRepository** (`asset_repository.py`)

**Responsibility**: Direct database access for `Asset` model

**Methods**:
- `create_asset()` - Insert new asset record
- `get_asset_by_id()` - Retrieve by UUID
- `get_asset_by_path()` - Retrieve by object path
- `list_user_assets()` - Query user's assets with filters
- `list_assets_by_session()` - Get assets for a generation session
- `list_style_assets()` - Query style templates
- `list_model_assets()` - Query model references
- `soft_delete_asset()` - Mark asset as inactive
- `update_asset_visibility()` - Toggle public/private

**Usage**:
```python
from sqlmodel import Session
from app.services.agent import AssetRepository

with Session(engine) as session:
    repo = AssetRepository(session)
    asset = repo.get_asset_by_id(asset_id)
```

---

### 2. **AssetService** (`asset_service.py`)

**Responsibility**: Business logic for asset management, coordinates storage + database

**Methods**:
- `upload_and_track_media()` - Upload generated image to MinIO + create DB record
- `upload_and_track_model()` - Upload model reference asset
- `upload_and_track_style()` - Upload style template with subcategory
- `get_user_media()` - Retrieve user's generated images
- `get_session_assets()` - Get all assets from a session
- `get_style_assets()` - List available styles
- `get_model_assets()` - List available models
- `delete_asset()` - Soft delete
- `toggle_asset_visibility()` - Update public/private status

**Usage**:
```python
from app.services.agent import AssetService

asset_service = AssetService(session)
asset = await asset_service.upload_and_track_media(
    user_id=user_id,
    filename="image.png",
    data=image_bytes,
    content_type="image/png",
    session_id=session_id,
    refined_prompt="A beautiful landscape",
)
```

**Key Features**:
- Handles MinIO upload failures gracefully
- Falls back to local filename when MinIO is disabled
- Automatically tracks file size, MIME type, and timestamps
- Links generated images to their source prompts and sessions

---

### 3. **AgentService** (`agent_service.py`)

**Responsibility**: Orchestrates complete image generation workflow

**Main Method**: `generate_image(request, user_id)`

**Workflow Steps**:
1. **Session Management**: Initialize or retrieve Google ADK session
2. **File Preparation**: Process uploaded images into payloads
3. **Prompt Processing**: Resolve category, style, and user prompt
4. **Agent Invocation**: Run AI agent for prompt refinement
5. **Image Generation**: Call Google Gemini with refined prompt
6. **Asset Storage**: Upload to MinIO + create database record
7. **Event Logging**: Track all steps in session events
8. **Error Handling**: Manage cancellations and failures with proper cleanup

**Usage**:
```python
from app.services.agent import AgentService, AssetService

asset_service = AssetService(session)
agent_service = AgentService(asset_service)

response = await agent_service.generate_image(
    request=ImageRequest(
        prompt="sunset over mountains",
        files=[uploaded_file],
        aspect_ratio=ImageAspectRatio.LANDSCAPE,
    ),
    user_id=current_user.id,
)
```

**Error Handling**:
- `asyncio.CancelledError` → Logs cancellation, marks session failed
- `Exception` → Logs error details, marks session failed, re-raises
- Success → Marks session completed, stores asset, returns response

---

## Route Layer (`app/routes/agent.py`)

**Responsibility**: HTTP interface, minimal logic

**Dependencies Injected**:
```python
def get_db_session() -> Generator[Session, None, None]:
    """Provides database session."""
    
def get_asset_service(db: Session = Depends(get_db_session)) -> AssetService:
    """Provides AssetService instance."""
    
def get_agent_service(
    asset_service: AssetService = Depends(get_asset_service)
) -> AgentService:
    """Provides AgentService instance."""
```

**Endpoints**:

### `POST /api/v1/agent/prompt`
Generate an image using AI agents.

**Request**:
- `prompt` (optional): User's text prompt
- `files`: 1-3 uploaded images
- `size`: Image dimensions (e.g., "1024x1024")
- `style`: Style preset (e.g., "polaroid")
- `aspect_ratio`: Aspect ratio (e.g., "16:9")
- `output_format`: PNG or JPEG
- `session_id` (optional): Continue existing session
- `category`: Routing category (creativity/template/fit/lightbox)

**Response**: `ImageResponse` with:
- Generated image (base64 encoded)
- Refined prompt
- Session ID
- Asset metadata

**Example**:
```bash
curl -X POST http://localhost:8000/api/v1/agent/prompt \
  -H "Authorization: Bearer $TOKEN" \
  -F "prompt=sunset over ocean" \
  -F "files=@photo.jpg" \
  -F "size=1024x1024" \
  -F "style=polaroid"
```

---

## Database Schema

The `Asset` model tracks all files in MinIO:

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | Primary key |
| `object_path` | String(500) | MinIO object path (unique, indexed) |
| `bucket_name` | String(100) | MinIO bucket (default: "jinuai-assets") |
| `asset_type` | Enum | `MEDIA`, `MODEL`, or `STYLE` |
| `style_subcategory` | String(50) | For styles: `fit`, `template`, `product` |
| `filename` | String(255) | Original filename |
| `mime_type` | String(50) | Content type (e.g., "image/png") |
| `file_size` | Integer | Size in bytes |
| `width` | Integer | Image width (optional) |
| `height` | Integer | Image height (optional) |
| `user_id` | UUID | Owner (foreign key → `user.id`) |
| `session_id` | String(100) | Google ADK session ID |
| `source_model_ids` | JSON | Array of model asset UUIDs used |
| `source_style_id` | UUID | Style asset used (foreign key → `asset.id`) |
| `refined_prompt` | String(2000) | AI-refined prompt text |
| `is_active` | Boolean | Soft delete flag |
| `is_public` | Boolean | Public gallery visibility |
| `created_at` | DateTime | Creation timestamp (indexed) |
| `updated_at` | DateTime | Last modification |
| `deleted_at` | DateTime | Soft delete timestamp |

**Indexes**: `asset_type`, `user_id`, `session_id`, `object_path`, `created_at`, `is_active`, `style_subcategory`

---

## Benefits of This Architecture

### 1. **Separation of Concerns**
- Routes handle HTTP, services handle logic, repositories handle data
- Each layer has a single, clear responsibility

### 2. **Testability**
- Services can be unit tested without HTTP layer
- Repositories can be tested with mock databases
- Easy to inject test doubles

### 3. **Reusability**
- `AssetService` can be used by other routes (e.g., `/media` upload)
- `AssetRepository` can be shared across services
- No duplication of business logic

### 4. **Maintainability**
- Changes to storage (MinIO → S3) only affect `AssetService`
- Changes to database schema only affect `AssetRepository`
- API changes only affect routes

### 5. **Dependency Injection**
- FastAPI dependencies provide automatic session management
- Services are created per-request with proper cleanup
- No global state or singletons

---

## Usage Examples

### Generate Image with Session Tracking
```python
# Client uploads photo + prompt
response = await agent_service.generate_image(
    request=ImageRequest(
        prompt="transform into anime style",
        files=[user_photo],
        style="polaroid",
        session_id="existing-session-123",
    ),
    user_id=user.id,
)

# Retrieve all assets from this session
assets = asset_service.get_session_assets(
    session_id="existing-session-123",
    user_id=user.id,
)
```

### List User's Generated Images
```python
media_assets = asset_service.get_user_media(
    user_id=user.id,
    limit=20,
    offset=0,
)

for asset in media_assets:
    print(f"{asset.filename}: {asset.refined_prompt}")
```

### Upload Style Template
```python
style_asset = await asset_service.upload_and_track_style(
    user_id=admin_user.id,
    filename="vintage-filter.png",
    data=image_bytes,
    content_type="image/png",
    style_subcategory="template",
)
```

---

## Testing

### Unit Tests
```python
# Test AssetRepository
def test_create_asset(session):
    repo = AssetRepository(session)
    asset = repo.create_asset(
        object_path="media/test.png",
        bucket_name="test-bucket",
        filename="test.png",
        asset_type=AssetType.MEDIA,
        mime_type="image/png",
        file_size=1024,
        user_id=test_user_id,
    )
    assert asset.id is not None
    assert asset.filename == "test.png"
```

### Integration Tests
```python
# Test AgentService workflow
@pytest.mark.asyncio
async def test_generate_image_workflow(session):
    asset_service = AssetService(session)
    agent_service = AgentService(asset_service)
    
    response = await agent_service.generate_image(
        request=mock_request,
        user_id=test_user_id,
    )
    
    assert response.status == ImageStatus.COMPLETED
    assert response.output_file.startswith("data:image")
```

---

## Future Enhancements

1. **Asset Metrics**: Track views, downloads, usage in generations
2. **Asset Versioning**: Keep history of edits/replacements
3. **Batch Operations**: Bulk delete, visibility toggle
4. **Asset Tags**: User-defined tags for organization
5. **Asset Search**: Full-text search on prompts and metadata
6. **CDN Integration**: Serve public assets via CDN
7. **Image Processing**: Automatic thumbnail generation, format conversion
8. **Quota Management**: Per-user storage limits

---

## Related Documentation

- **Migration Guide**: `alembic/CLAUDE.md`
- **Agent Helpers**: `app/utils/AGENTS.md`
- **Project Overview**: `AGENTS.md` (root)
- **MinIO Storage**: `app/utils/minio_storage.py`
