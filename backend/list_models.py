import asyncio
import os
from dotenv import load_dotenv
import google.generativeai as genai

async def list_models():
    load_dotenv()
    key = os.getenv("GEMINI_API_KEY")
    genai.configure(api_key=key)
    for m in genai.list_models():
        if 'generateContent' in m.supported_generation_methods:
            print(m.name)

if __name__ == "__main__":
    asyncio.run(list_models())
