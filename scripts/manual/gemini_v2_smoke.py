import os
from dotenv import load_dotenv
from google import genai

# Load environment variables
load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise SystemExit("GEMINI_API_KEY is not configured")

try:
    # Configure ด้วย package ใหม่
    client = genai.Client(api_key=GEMINI_API_KEY)

    # Test connection ด้วย model ที่ถูกต้อง
    response = client.models.generate_content(
        model="gemini-2.0-flash-exp",
        contents="Hello, test connection"
    )

    print("✅ Gemini API connection successful!")
    print(f"📝 Response: {response.text[:100]}...")

    # แสดง models ที่มี
    print("\n🔍 ดู models ที่มี:")
    for model in client.models.list():
        if "generateContent" in model.supported_actions:
            print(f"  - {model.name}")

except Exception as e:
    print(f"❌ Error: {str(e)}")
    print("\n💡 ลองใช้ model อื่น:")
    print("  - gemini-2.0-flash-exp")
    print("  - gemini-1.5-pro")
    print("  - gemini-1.0-pro")
