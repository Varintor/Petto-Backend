import os
import time
import uuid
from typing import List
from fastapi import APIRouter, Depends, File, UploadFile, Form, HTTPException
from sqlalchemy.orm import Session
from supabase import create_client, Client
from google import genai

from app import models, schemas
from app.database import SessionLocal, get_db

router = APIRouter(
    prefix="/api/v1",
    tags=["Health Assessments"],
)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL and SUPABASE_KEY else None

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
gemini_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

# ==========================================
# GET Endpoints
# ==========================================

@router.get("/assessments", response_model=List[schemas.AssessmentResponse])
def get_all_assessments(db: Session = Depends(get_db)):
    """List all assessments."""
    assessments = db.query(models.HealthAssessment).order_by(models.HealthAssessment.created_at.desc()).all()
    return assessments


@router.get("/assessments/{assessment_id}", response_model=schemas.AssessmentResponse)
def get_assessment(assessment_id: int, db: Session = Depends(get_db)):
    """Get a single assessment by ID."""
    assessment = db.query(models.HealthAssessment).filter(models.HealthAssessment.id == assessment_id).first()
    if not assessment:
        raise HTTPException(status_code=404, detail="Assessment not found")
    return assessment


@router.get("/pets/{pet_id}/assessments", response_model=List[schemas.AssessmentResponse])
def get_pet_assessments(pet_id: int, db: Session = Depends(get_db)):
    """List all assessments for a specific pet."""
    pet = db.query(models.Pet).filter(models.Pet.id == pet_id).first()
    if not pet:
        raise HTTPException(status_code=404, detail="Pet not found")

    assessments = db.query(models.HealthAssessment).filter(
        models.HealthAssessment.pet_id == pet_id
    ).order_by(models.HealthAssessment.created_at.desc()).all()

    return assessments


# ==========================================
# POST Endpoint
# ==========================================

@router.post("/assessments", response_model=schemas.AssessmentResponse)
async def create_assessment(
    pet_id: int = Form(...),
    symptom_description: str = Form(...),
    image: UploadFile = File(...),
):
    # No Depends(get_db) here — Supabase upload + Gemini take 5-30s and would
    # otherwise hold a pooled DB connection idle that whole time, draining the
    # pool under concurrent load. We open a short-lived session at the end
    # only when there's actually a row to insert.
    if not image.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")

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

    # 2. Analyse image + symptoms with Gemini
    ai_risk_level = models.RiskLevel.MODERATE
    ai_response_text = "AI service unavailable"

    if gemini_client:
        try:
            prompt = f"""You are a veterinary triage assistant. Your role is to assess risk from the photo and symptom description provided by a pet owner. Always err on the side of caution.

Symptom description from the owner: "{symptom_description}"

Respond in English only. Do not use emoji. Use the following structure:

1. OBSERVATIONS
What abnormalities do you observe in the image and the description? Be specific about visible signs (swelling, redness, discharge, posture, etc.).

2. POTENTIAL CONCERNS
What health issues could these signs indicate? Group by likelihood. Avoid diagnosing a specific disease — describe the category of concern instead (e.g. "dermatological irritation", "gastrointestinal distress").

3. RECOMMENDED ACTIONS
What should the owner do right now?
- DO: List concrete first-aid or monitoring steps.
- DO NOT: List actions that could worsen the condition.
- URGENCY: State clearly whether the pet should see a vet immediately, within 24 hours, or can be monitored at home.

4. DISCLAIMER
State that this is a preliminary screening tool, not a veterinary diagnosis. A licensed veterinarian should examine the pet for any definitive assessment.

Risk level criteria (when uncertain, always round UP to the higher level):
- HIGH: Life-threatening or emergency (difficulty breathing, heavy bleeding, seizures, suspected poisoning, severe trauma, sudden facial swelling, eye injury) — requires immediate veterinary attention.
- MODERATE: Abnormal symptoms needing professional evaluation (lethargy, appetite loss, moderate wounds, persistent vomiting/diarrhea, limping) — should see a vet within 24 hours.
- LOW: Minor symptoms (small scratches, mild flea presence, normal shedding, minor ear wax) — can be monitored at home with basic care.

On the very last line of your response, output exactly one of these (nothing else on that line):
Risk: LOW
Risk: MODERATE
Risk: HIGH"""

            # Retry with backoff on transient 503/429 errors
            contents = [
                prompt,
                {
                    "inline_data": {
                        "mime_type": image.content_type,
                        "data": file_bytes
                    }
                }
            ]
            response = None
            last_err = None
            for attempt in range(4):
                try:
                    response = gemini_client.models.generate_content(
                        model='models/gemini-flash-latest',
                        contents=contents
                    )
                    break
                except Exception as retry_err:
                    last_err = retry_err
                    msg = str(retry_err)
                    if any(s in msg for s in ("503", "UNAVAILABLE", "overload", "high demand", "429")):
                        time.sleep(1.5 * (attempt + 1))
                        continue
                    raise
            if response is None:
                raise last_err

            ai_response_text = response.text

            last_line = ai_response_text.strip().rsplit("\n", 1)[-1].strip().upper()
            if "HIGH" in last_line:
                ai_risk_level = models.RiskLevel.HIGH
            elif "LOW" in last_line:
                ai_risk_level = models.RiskLevel.LOW
            else:
                ai_risk_level = models.RiskLevel.MODERATE

        except Exception as e:
            ai_response_text = f"AI analysis failed: {str(e)}"

    # Open the DB session only now that the slow work (Supabase upload + Gemini
    # call) is complete. The connection is held for <1s instead of 5-30s.
    with SessionLocal() as db:
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
        # Detach so the caller can serialize the ORM object after the session
        # closes (FastAPI's response_model will read attributes off it).
        db.expunge(new_assessment)
        return new_assessment