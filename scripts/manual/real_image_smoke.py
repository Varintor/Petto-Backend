import os
import base64
from dotenv import load_dotenv
from google import genai

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise SystemExit("GEMINI_API_KEY is not configured")
client = genai.Client(api_key=GEMINI_API_KEY)

# สร้างรูปจริงๆ แบบง่าย (1x1 pixel red PNG)
print("🖼️ สร้างรูปทดสอบ...")
png_data = base64.b64decode("""
iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg==
""")

print(f"📊 ขนาดรูป: {len(png_data)} bytes")

# วิธีที่ 1: ใช้ Blob กับ MIME type
try:
    print("🧪 วิธีที่ 1: Blob + MIME type...")
    response = client.models.generate_content(
        model='models/gemini-flash-latest',
        contents=[
            "What do you see in this image?",
            genai.types.Blob(
                data=png_data,
                mime_type="image/png"
            )
        ]
    )
    print(f"✅ วิธีที่ 1 สำเร็จ!")
    print(f"📝 Response: {response.text}")
except Exception as e:
    print(f"❌ วิธีที่ 1 ล้มเหลว: {str(e)}")

    # วิธีที่ 2: ใช้ dict format แบบง่าย
    try:
        print("\n🧪 วิธีที่ 2: Simple dict...")
        response = client.models.generate_content(
            model='models/gemini-flash-latest',
            contents=[
                "What do you see?",
                {
                    "inline_data": {
                        "mime_type": "image/png",
                        "data": png_data
                    }
                }
            ]
        )
        print(f"✅ วิธีที่ 2 สำเร็จ!")
        print(f"📝 Response: {response.text}")
    except Exception as e2:
        print(f"❌ วิธีที่ 2 ล้มเหลว: {str(e2)}")

        # วิธีที่ 3: ใช้ base64 data
        try:
            print("\n🧪 วิธีที่ 3: Base64 encoded...")
            b64_data = base64.b64encode(png_data).decode('utf-8')
            response = client.models.generate_content(
                model='models/gemini-flash-latest',
                contents=[
                    "What do you see?",
                    {
                        "inline_data": {
                            "mime_type": "image/png",
                            "data": b64_data
                        }
                    }
                ]
            )
            print(f"✅ วิธีที่ 3 สำเร็จ!")
            print(f"📝 Response: {response.text}")
        except Exception as e3:
            print(f"❌ วิธีที่ 3 ล้มเหลว: {str(e3)}")
