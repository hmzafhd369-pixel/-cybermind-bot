import google.generativeai as genai
import os
from dotenv import load_dotenv

load_dotenv("/home/ubuntu/almihwar_bot/bot_config_2.env")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    print("Available models:")
    for m in genai.list_models():
        if 'generateContent' in m.supported_generation_methods:
            print(m.name)
else:
    print("GEMINI_API_KEY not found.")
