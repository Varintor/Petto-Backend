import os
from dotenv import load_dotenv
from google import genai

# Load environment variables
load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise SystemExit("GEMINI_API_KEY is not configured")

try:
    client = genai.Client(api_key=GEMINI_API_KEY)
    response = client.models.generate_content(
        model="models/gemini-flash-latest",
        contents="Hello, test connection",
    )

    print("✅ Gemini API connection successful!")
    print(f"📝 Response: {response.text[:100]}...")

except Exception as e:
    print(f"❌ Error: {str(e)}")
    print("\n💡 แนะนำให้:")
    print("1. ตรวจสอบว่าได้เปิดใช้งาน Gemini API ใน Google Cloud Console หรือยัง")
    print("2. ตรวจสอบว่า API Key ถูกต้องหรือไม่")
    print("3. ตรวจสอบว่ามีการตั้งค่า API Key restrictions หรือไม่")
