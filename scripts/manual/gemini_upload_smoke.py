import os
from dotenv import load_dotenv
from google import genai

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise SystemExit("GEMINI_API_KEY is not configured")

try:
    client = genai.Client(api_key=GEMINI_API_KEY)

    # ทดสอบส่งข้อความธรรมดาก่อน
    print("🧪 ทดสอบส่งข้อความธรรมดา...")
    response = client.models.generate_content(
        model='models/gemini-2.0-flash-lite',
        contents="Hello, test connection"
    )
    print("✅ ส่งข้อความได้:", response.text[:50])

    # สร้างไฟล์ทดสอบ (รูป dummy)
    print("\n🖼️ ทดสอบส่งรูปภาพ...")
    test_image_data = b"fake_image_data_for_testing"

    # วิธีที่ 1: ใช้ Blob
    try:
        response = client.models.generate_content(
            model='models/gemini-2.0-flash-lite',
            contents=[
                "Describe this image",
                genai.types.Blob(
                    data=test_image_data,
                    mime_type="image/jpeg"
                )
            ]
        )
        print("✅ วิธีที่ 1 (Blob) ใช้ได้!")
    except Exception as e:
        print(f"❌ วิธีที่ 1 (Blob) ล้มเหลว: {e}")

        # วิธีที่ 2: ใช้ dict format
        try:
            response = client.models.generate_content(
                model='models/gemini-2.0-flash-lite',
                contents=[
                    "Describe this image",
                    {
                        "inline_data": {
                            "data": test_image_data,
                            "mime_type": "image/jpeg"
                        }
                    }
                ]
            )
            print("✅ วิธีที่ 2 (dict format) ใช้ได้!")
        except Exception as e2:
            print(f"❌ วิธีที่ 2 (dict format) ล้มเหลว: {e2}")

        # วิธีที่ 3: ใช้ Parts structure
        try:
            response = client.models.generate_content(
                model='models/gemini-2.0-flash-lite',
                contents=[
                    {
                        "parts": [
                            {"text": "Describe this image"},
                            {
                                "inline_data": {
                                    "data": test_image_data,
                                    "mime_type": "image/jpeg"
                                }
                            }
                        ]
                    }
                ]
            )
            print("✅ วิธีที่ 3 (Parts structure) ใช้ได้!")
        except Exception as e3:
            print(f"❌ วิธีที่ 3 (Parts structure) ล้มเหลว: {e3}")

except Exception as e:
    print(f"❌ Error: {str(e)}")
