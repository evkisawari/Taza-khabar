import google.generativeai as genai
import os
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=api_key)

available = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
print(available)
