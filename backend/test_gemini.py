import asyncio
import os
from dotenv import load_dotenv
import google.generativeai as genai

async def test_gemini():
    load_dotenv()
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        print("❌ No API Key found in .env")
        return

    print(f"Key found: {key[:10]}...")
    genai.configure(api_key=key)
    model = genai.GenerativeModel('gemini-2.0-flash')
    
    try:
        response = await model.generate_content_async("Say 'Gemini is Ready'")
        print(f"AI Response: {response.text.strip()}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_gemini())
