## Overview

This project is an **AI-powered image generation application** that allows users to create high-quality images using Google's advanced AI model codenamed **Nano Banana**.  

It supports multiple modes including:

- **Creative Mode:** Generate images from scratch based on user prompts.  
- **Fitting Mode:** Modify existing images to fit new styles or concepts.  
- **Lightbox (Product) Mode:** Showcase and edit product images.  
- **Style (Template) Mode:** Apply predefined templates or styles to images.  

> ⚠️ **Important:** This project **requires the GOOGLE_AI_SDK** to function properly.  
>  
> 🛠️ Agents are built using **Google A2A (Agent-to-Agent) agentic tool**, following the official [Google Agent Team Tutorial](https://google.github.io/adk-docs/tutorials/agent-team/).  
>  
> 📚 For reference on image generation APIs, see [Google Gemini Image Generation Documentation](https://ai.google.dev/gemini-api/docs/image-generation).

## Core Files

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
