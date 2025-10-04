# AI-Powered Image Generation Application

## Overview

This project is an **AI-powered image generation application** that enables users to create **high-quality images** using Google’s advanced AI model codenamed **Nano Banana**.  

### Supported Modes
- **Creative Mode** – Generate images from scratch based on user prompts.  
- **Fitting Mode** – Modify existing images to fit new styles or concepts.  
- **Lightbox (Product) Mode** – Showcase and edit product images.  
- **Style (Template) Mode** – Apply predefined templates or styles to images.  

### Requirements & References
> ⚠️ **Important:** This project **requires the `GOOGLE_AI_SDK`** to function properly.  

🛠️ Agents are built using **Google A2A (Agent-to-Agent)** tools, following the official [Google Agent Team Tutorial](https://google.github.io/adk-docs/tutorials/agent-team/).  

📚 For API reference, see [Google Gemini Image Generation Documentation](https://ai.google.dev/gemini-api/docs/image-generation).  

💡 **Tip:** When making decisions on **session management**, check what the provider gives out-of-the-box (e.g., OpenAI Agents SDK or Google A2A).  

## Object Storage (MinIO)

Generated images and reusable assets can be synced to a MinIO cluster in addition to the local `generated-img/` folder. Configure the storage client through the following environment variables:

```
MINIO_ENDPOINT=<host:port>
MINIO_ACCESS_KEY=<access-key>
MINIO_SECRET_KEY=<secret-key>
MINIO_REGION=<optional-region>
MINIO_SECURE=<true|false>
MINIO_BUCKET_NAME=jinuai-assets
MINIO_PREFIX_MODELS=models
MINIO_PREFIX_STYLES=styles
MINIO_PREFIX_MEDIA=media
```

When enabled, the API writes:
- `models/` – checkpoints or artifact uploads.
- `styles/fit|template|product/` – curated style references.
- `media/<user-id>/` – generated images associated with each user for powering "My Media" views on the frontend.

The service creates placeholder objects so the folder layout is visible immediately within the MinIO console.

## Agent Built-in Session Service (Database Schema)

| Table        | Key Fields                                                                 |
|--------------|----------------------------------------------------------------------------|
| **sessions** | `id`, `app_name`, `user_id`, `state`, `create_time`, `update_time`         |
| **events**   | `id`, `app_name`, `user_id`, `session_id`, `invocation_id`, `author`, `actions`, `branch`, `timestamp`, `content`, `grounding_metadata`, `custom_metadata`, `partial`, `turn_complete`, `error_code`, `error_message`, `interrupted` |
| **app_states** | `app_name`, `state`, `update_time`                                       |
| **user_states** | `app_name`, `user_id`, `state`, `update_time`                           |

## Core File Structure

```text
📂 app
├── 📂 routes
│   ├── 📄 agent.py
│   └── 📄 style.json
├── 📂 utils
│   ├── 📄 agent_guardrail.py
│   ├── 📄 agent_helpers.py
│   ├── 📄 agent_orchestration.py
│   └── 📄 agent_tool.py
│   └── 📄 config.py
```

## Model Selection

FLASH_TEXT: ClassVar[str] = "gemini-2.5-flash"
FLASH_IMAGE: ClassVar[str] = "gemini-2.5-flash-image-preview"

> Change the model to your liking

## Project Philosophy

This repository is designed not just for research and implementation of machine learning tools, but also to support a continuous cycle of applied AI collaboration:
Awareness – Understanding goals, platforms, and how to delegate effectively between humans and AI.
Description – Defining expectations, task approaches, and AI collaboration behavior.
Discernment – Evaluating the quality of outputs, the soundness of processes, and AI performance.
Diligence – Ensuring responsible use of AI, maintaining transparency, and taking accountability for deployed outputs.
