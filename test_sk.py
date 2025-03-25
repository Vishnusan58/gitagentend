import os

import semantic_kernel as sk
from semantic_kernel.connectors.ai.google.google_ai import GoogleAIChatCompletion

try:
    kernel = sk.Kernel.Builder().build()
    api_key =os.getenv("GEMINI_API")  # REPLACE WITH YOUR ACTUAL KEY
    kernel.add_chat_service("gemini", GoogleAIChatCompletion("gemini-1.5-pro", api_key))
    print("Semantic Kernel initialized successfully!")
except Exception as e:
    print(f"Error initializing Semantic Kernel: {e}")