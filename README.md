# AI-Powered Image Generation Application

## Overview

This project is an **AI-powered image generation application** that enables users to create **high-quality images** using Google’s advanced AI model codenamed **Nano Banana**.  

### Supported Modes
- **Creative Mode** – Generate images from scratch based on user prompts.  
- **Fitting Mode** – Modify existing images to fit new styles or concepts.  
- **Lightbox (Product) Mode** – Showcase and edit product images.  
- **Style (Template) Mode** – Apply predefined templates or styles to images.  

---

### Requirements & References
> ⚠️ **Important:** This project **requires the `GOOGLE_AI_SDK`** to function properly.  

🛠️ Agents are built using **Google A2A (Agent-to-Agent)** tools, following the official [Google Agent Team Tutorial](https://google.github.io/adk-docs/tutorials/agent-team/).  

📚 For API reference, see [Google Gemini Image Generation Documentation](https://ai.google.dev/gemini-api/docs/image-generation).  

💡 **Tip:** When making decisions on **session management**, check what the provider gives out-of-the-box (e.g., OpenAI Agents SDK or Google A2A).  

---

## Agent Built-in Session Service (Database Schema)

### Tables

#### `sessions`
- **id**
- **app_name**
- **user_id**
- **state**
- **create_time**
- **update_time**

#### `events`
- **id**
- **app_name**
- **user_id**
- **session_id**
- **invocation_id**
- **author**
- **actions**
- **branch**
- **timestamp**
- **content**
- **grounding_metadata**
- **custom_metadata**
- **partial**
- **turn_complete**
- **error_code**
- **error_message**
- **interrupted**

#### `app_states`
- **app_name**
- **state**
- **update_time**

#### `user_states`
- **app_name**
- **user_id**
- **state**
- **update_time**

---

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
```

## Project Philosophy

This repository is designed not just for research and implementation of machine learning tools, but also to support a continuous cycle of applied AI collaboration:
Awareness – Understanding goals, platforms, and how to delegate effectively between humans and AI.
Description – Defining expectations, task approaches, and AI collaboration behavior.
Discernment – Evaluating the quality of outputs, the soundness of processes, and AI performance.
Diligence – Ensuring responsible use of AI, maintaining transparency, and taking accountability for deployed outputs.
