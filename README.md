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
```

## Summary

The idea behind this repository is not only for the author to research and implement appropriate machine learning tools, but also to move from simply outlining the elements of working with AI to applying them effectively as part of a continuous cycle. The process begins with **awareness**, where the author focuses on understanding goals, the platforms being used, and how best to delegate tasks between humans and AI. Building on that foundation, it moves into **description**, clearly defining what is wanted, how the AI should approach the work, and how it should behave during collaboration. With outputs in hand, the author then turns to **discernment**, carefully evaluating the quality of the product, the soundness of the process, and the effectiveness of the AI’s performance. Finally, the cycle is completed with **diligence**, ensuring thoughtful use of AI systems, maintaining transparency about their role, and taking responsibility for the outputs deployed.
