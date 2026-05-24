import os
import uuid
from typing import List
from fastapi import APIRouter, Depends, File, UploadFile, Form, HTTPException
from sqlalchemy.orm import Session
from supabase import create_client, Client
from google import genai

from app import models, schemas
from app.database import get_db

router = APIRouter(
    prefix="/api/v1",
    tags=["Health Assessments (ประเมินสุขภาพด้วย AI)"]
)

# --- ตั้งค่า Supabase ---
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL and SUPABASE_KEY else None

# --- ตั้งค่า Gemini AI (ใช้ package ใหม่) ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
gemini_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

# ==========================================
# GET Endpoints - ดูข้อมูลการประเมิน
# ==========================================

@router.get("/assessments", response_model=List[schemas.AssessmentResponse])
def get_all_assessments(db: Session = Depends(get_db)):
    """
    ดูการประเมินทั้งหมดในระบบ
    """
    assessments = db.query(models.HealthAssessment).order_by(models.HealthAssessment.created_at.desc()).all()
    return assessments


@router.get("/assessments/{assessment_id}", response_model=schemas.AssessmentResponse)
def get_assessment(assessment_id: int, db: Session = Depends(get_db)):
    """
    ดูรายละเอียดการประเมินรายการเดียว
    """
    assessment = db.query(models.HealthAssessment).filter(models.HealthAssessment.id == assessment_id).first()
    if not assessment:
        raise HTTPException(status_code=404, detail="ไม่พบการประเมินในระบบ")
    return assessment


@router.get("/pets/{pet_id}/assessments", response_model=List[schemas.AssessmentResponse])
def get_pet_assessments(pet_id: int, db: Session = Depends(get_db)):
    """
    ดูประวัติการประเมินทั้งหมดของสัตว์เลี้ยงตัวหนึ่ง
    """
    pet = db.query(models.Pet).filter(models.Pet.id == pet_id).first()
    if not pet:
        raise HTTPException(status_code=404, detail="ไม่พบสัตว์เลี้ยงในระบบ")

    assessments = db.query(models.HealthAssessment).filter(
        models.HealthAssessment.pet_id == pet_id
    ).order_by(models.HealthAssessment.created_at.desc()).all()

    return assessments


# ==========================================
# POST Endpoint - สร้างการประเมินใหม่
# ==========================================

@router.post("/assessments", response_model=schemas.AssessmentResponse)
async def create_assessment(
    pet_id: int = Form(...),
    symptom_description: str = Form(...),
    image: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    if not image.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")

    # 1. จัดการอัปโหลดไฟล์ไป Supabase
    try:
        file_bytes = await image.read()
        file_extension = image.filename.split(".")[-1]
        unique_filename = f"{pet_id}_{uuid.uuid4().hex}.{file_extension}"
        
        supabase.storage.from_("pet-images").upload(
            path=unique_filename, file=file_bytes, file_options={"content-type": image.content_type}
        )
        actual_image_uri = supabase.storage.from_("pet-images").get_public_url(unique_filename)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

    # 2. ส่งภาพและอาการให้ Gemini วิเคราะห์ (ใช้ package ใหม่)
    ai_risk_level = models.RiskLevel.MODERATE
    ai_response_text = "ไม่สามารถเชื่อมต่อ AI ได้"

    if gemini_client:
        try:
            prompt = f"""
            ในฐานะผู้เชี่ยวชาญด้านการคัดกรองอาการสัตว์เลี้ยงเบื้องต้น (Veterinary Triage Assistant)
            หน้าที่ของคุณคือการประเมินความเสี่ยงจากข้อมูลและภาพถ่ายที่เจ้าของสัตว์เลี้ยงส่งมาให้ "อย่างระมัดระวังและปลอดภัยที่สุด"

            ข้อมูลอาการที่เจ้าของแจ้ง: "{symptom_description}"

            กรุณาวิเคราะห์และตอบกลับตามหัวข้อดังต่อไปนี้อย่างละเอียดและเข้าใจง่าย:

            1. 🔍 การประเมินเบื้องต้น (Observations): คุณสังเกตเห็นความผิดปกติอะไรจากภาพและข้อความบ้าง
            2. 🩺 ความเป็นไปได้ของอาการ (Potential Issues): อาการเหล่านี้อาจบ่งบอกถึงปัญหาสุขภาพกลุ่มใด (ระบุเป็นกลุ่มความเสี่ยง หลีกเลี่ยงการฟันธงโรคเจาะจงเพื่อความปลอดภัย)
            3. 💡 คำแนะนำในการดูแลเบื้องต้น (First-aid & Next Steps): เจ้าของสัตว์เลี้ยงควรทำอย่างไรในขณะนี้ (ระบุสิ่งที่ "ควรทำ" และสิ่งที่ "ห้ามทำเด็ดขาด" เพื่อป้องกันอันตราย)
            4. ⚠️ ข้อควรระวัง (Disclaimer): ย้ำเตือนว่านี่เป็นเพียงการคัดกรองเบื้องต้น ไม่ใช่การวินิจฉัยทางการแพทย์

            เกณฑ์การประเมินระดับความเสี่ยง:
            (กฎสำคัญ: หากมีอาการที่ก้ำกึ่ง หรือไม่แน่ใจในความรุนแรง ให้ปรับระดับความเสี่ยงเป็นระดับที่สูงกว่าเสมอ เพื่อความปลอดภัยสูงสุดของสัตว์เลี้ยง)
            - HIGH: ภาวะฉุกเฉินถึงชีวิต (เช่น หายใจลำบาก, เลือดออกมาก, อุบัติเหตุรุนแรง, โดนสารพิษ, ชักเกร็ง, หน้าบวมพองเฉียบพลัน, อุบัติเหตุที่ตา) -> ต้องพบสัตวแพทย์ "ทันที"
            - MODERATE: อาการผิดปกติที่ควรได้รับการตรวจ (เช่น ซึม, ไม่กินอาหาร, บาดแผลขนาดกลาง, อาเจียน/ท้องเสียติดต่อกัน) -> ควรพบสัตวแพทย์ในเวลาทำการ
            - LOW: อาการเล็กน้อย (เช่น รอยขีดข่วนตื้นๆ, เห็บหมัดเล็กน้อย, ขนร่วงปกติ) -> สามารถดูแลเบื้องต้นและสังเกตอาการที่บ้านได้

            กรุณาสรุประดับความเสี่ยงใน "บรรทัดสุดท้าย" ของคำตอบ โดยต้องพิมพ์คำใดคำหนึ่งต่อไปนี้เป๊ะๆ เท่านั้น (ห้ามมีเครื่องหมายหรือข้อความอื่นต่อท้าย):
            ความเสี่ยง: LOW
            ความเสี่ยง: MODERATE
            ความเสี่ยง: HIGH
            """

            # ใช้ model และวิธีส่งรูปที่ถูกต้อง
            response = gemini_client.models.generate_content(
                model='models/gemini-flash-latest',
                contents=[
                    prompt,
                    {
                        "inline_data": {
                            "mime_type": image.content_type,
                            "data": file_bytes
                        }
                    }
                ]
            )
            ai_response_text = response.text

            if "HIGH" in ai_response_text.upper():
                ai_risk_level = models.RiskLevel.HIGH
            elif "LOW" in ai_response_text.upper():
                ai_risk_level = models.RiskLevel.LOW
            else:
                ai_risk_level = models.RiskLevel.MODERATE

        except Exception as e:
            ai_response_text = f"เกิดข้อผิดพลาดจาก AI: {str(e)}"

    # 3. บันทึกข้อมูลลงฐานข้อมูล
    new_assessment = models.HealthAssessment(
        pet_id=pet_id,
        symptom_description=symptom_description,
        image_uri=actual_image_uri,
        risk_level=ai_risk_level,
        ai_raw_response=ai_response_text
    )
    
    db.add(new_assessment)
    db.commit()
    db.refresh(new_assessment)

    return new_assessment