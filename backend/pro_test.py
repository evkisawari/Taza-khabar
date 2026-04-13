import google.generativeai as genai
import os
import httpx
import trafilatura
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")

async def test_pro_max():
    print("PRO MAX REAL-WORLD TEST...")
    
    # 1. TEST GEMINI GENERATION
    print("\n[1/2] Testing AI Summarization...")
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content("Say 'The New Key is Working Pro Max' if you can read this.")
        print(f"AI Response: {response.text}")
    except Exception as e:
        print(f"Gemini Error: {e}")

    # 2. TEST GOOGLE NEWS (Because NDTV is blocked)
    print("\n[2/2] Checking Google News RSS...")
    url = "https://news.google.com/rss?hl=en-IN&gl=IN&ceid=IN:en"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
            print(f"Google News Response: {resp.status_code}")
            if resp.status_code == 200:
                print("Google News is accessible!")
    except Exception as e:
        print(f"RSS Error: {e}")

if __name__ == "__main__":
    import asyncio
    asyncio.run(test_pro_max())
