import asyncio
import logging
import os
from typing import List
from fastapi import APIRouter, Depends, File, UploadFile, Form, HTTPException
from sqlalchemy.orm import Session
from google import genai

from app import models, schemas
from app.auth import (
    SupabaseAuthContext,
    get_current_user,
    get_supabase_auth_context,
    require_owned_pet,
)
from app.database import get_db, get_session_factory
from app.storage import (
    StorageConfigurationError,
    assessment_object_path,
    create_assessment_signed_url,
    create_user_storage_client,
)

router = APIRouter(
    prefix="/api/v1",
    tags=["Health Assessments"],
)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
gemini_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

logger = logging.getLogger("petto.assessments")
MAX_IMAGE_BYTES = int(os.getenv("MAX_ASSESSMENT_IMAGE_BYTES", 10 * 1024 * 1024))
EXTERNAL_TIMEOUT_SECONDS = float(
    os.getenv("ASSESSMENT_EXTERNAL_TIMEOUT_SECONDS", "30")
)
AI_RETRY_BASE_SECONDS = float(
    os.getenv("ASSESSMENT_AI_RETRY_BASE_SECONDS", "1.5")
)

_IMAGE_SIGNATURES = (
    ("image/jpeg", ".jpg", lambda data: data.startswith(b"\xff\xd8\xff")),
    ("image/png", ".png", lambda data: data.startswith(b"\x89PNG\r\n\x1a\n")),
    (
        "image/webp",
        ".webp",
        lambda data: len(data) >= 12
        and data.startswith(b"RIFF")
        and data[8:12] == b"WEBP",
    ),
)


def _assessment_response(assessment, access_token: str) -> schemas.AssessmentResponse:
    payload = schemas.AssessmentResponse.model_validate(assessment)
    if payload.image_uri:
        try:
            payload.image_uri = create_assessment_signed_url(access_token, payload.image_uri)
        except Exception:
            logger.exception("Could not sign assessment image id=%s", assessment.id)
            payload.image_uri = None
    return payload


def _validated_image_type(data: bytes) -> tuple[str, str] | None:
    for mime_type, extension, matches in _IMAGE_SIGNATURES:
        if matches(data):
            return mime_type, extension
    return None


async def _run_blocking(callable_):
    return await asyncio.wait_for(
        asyncio.to_thread(callable_), timeout=EXTERNAL_TIMEOUT_SECONDS
    )

# ==========================================
# GET Endpoints
# ==========================================

@router.get("/assessments", response_model=List[schemas.AssessmentResponse])
def get_my_assessments(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    auth_context: SupabaseAuthContext = Depends(get_supabase_auth_context),
):
    """List all assessments across the caller's pets."""
    assessments = db.query(models.HealthAssessment).join(
        models.Pet, models.HealthAssessment.pet_id == models.Pet.id
    ).filter(
        models.Pet.user_id == current_user.id
    ).order_by(models.HealthAssessment.created_at.desc()).all()
    return [_assessment_response(a, auth_context.access_token) for a in assessments]


@router.get("/assessments/{assessment_id}", response_model=schemas.AssessmentResponse)
def get_assessment(
    assessment_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    auth_context: SupabaseAuthContext = Depends(get_supabase_auth_context),
):
    """Get a single assessment by ID (owner only)."""
    assessment = db.query(models.HealthAssessment).filter(models.HealthAssessment.id == assessment_id).first()
    if not assessment:
        raise HTTPException(status_code=404, detail="Assessment not found")
    require_owned_pet(assessment.pet_id, current_user, db)
    return _assessment_response(assessment, auth_context.access_token)


@router.get("/pets/{pet_id}/assessments", response_model=List[schemas.AssessmentResponse])
def get_pet_assessments(
    pet_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    auth_context: SupabaseAuthContext = Depends(get_supabase_auth_context),
):
    """List all assessments for a specific pet (owner only)."""
    require_owned_pet(pet_id, current_user, db)

    assessments = db.query(models.HealthAssessment).filter(
        models.HealthAssessment.pet_id == pet_id
    ).order_by(models.HealthAssessment.created_at.desc()).all()

    return [_assessment_response(a, auth_context.access_token) for a in assessments]


# ==========================================
# POST Endpoint
# ==========================================

@router.post("/assessments", response_model=schemas.AssessmentResponse)
async def create_assessment(
    pet_id: int = Form(...),
    symptom_description: str = Form(...),
    image: UploadFile = File(...),
    auth_context: SupabaseAuthContext = Depends(get_supabase_auth_context),
    session_factory=Depends(get_session_factory),
):
    # No Depends(get_db) here — Supabase upload + Gemini take 5-30s and would
    # otherwise hold a pooled DB connection idle that whole time, draining the
    # pool under concurrent load. Auth uses get_supabase_auth_context (token
    # check only, no DB); user lookup + pet ownership run in a short-lived
    # session below.
    if not (image.content_type or "").startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")

    # Ownership check up-front, then release the connection before slow work.
    with session_factory() as db:
        current_user = db.query(models.User).filter(
            models.User.supabase_uid == auth_context.supabase_uid
        ).first()
        if not current_user:
            raise HTTPException(status_code=401, detail="User not found")
        require_owned_pet(pet_id, current_user, db)

    try:
        file_bytes = await image.read(MAX_IMAGE_BYTES + 1)
        if len(file_bytes) > MAX_IMAGE_BYTES:
            raise HTTPException(status_code=413, detail="Image is too large")

        validated_type = _validated_image_type(file_bytes)
        if validated_type is None:
            raise HTTPException(
                status_code=400,
                detail="Unsupported or invalid image. Use JPEG, PNG, or WebP.",
            )
        mime_type, extension = validated_type
        unique_filename = assessment_object_path(
            auth_context.supabase_uid,
            pet_id,
            extension,
        )

        try:
            storage_client = create_user_storage_client(auth_context.access_token)
        except StorageConfigurationError:
            raise HTTPException(status_code=503, detail="Image storage is unavailable")
        bucket = storage_client.from_("pet-images")
        await _run_blocking(
            lambda: bucket.upload(
                path=unique_filename,
                file=file_bytes,
                file_options={"content-type": mime_type},
            )
        )
    except HTTPException:
        raise
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Image upload timed out")
    except Exception:
        logger.exception("Assessment image upload failed for pet_id=%s", pet_id)
        raise HTTPException(status_code=502, detail="Image upload failed")

    # 2. Analyse image + symptoms with Gemini
    ai_risk_level = None
    ai_response_text = None
    assessment_status = "failed"
    error_code = "AI_SERVICE_UNAVAILABLE"

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
                        "mime_type": mime_type,
                        "data": file_bytes
                    }
                }
            ]
            response = None
            last_err = None
            for attempt in range(4):
                try:
                    response = await _run_blocking(
                        lambda: gemini_client.models.generate_content(
                            model='models/gemini-flash-latest',
                            contents=contents,
                        )
                    )
                    break
                except Exception as retry_err:
                    last_err = retry_err
                    msg = str(retry_err)
                    if any(s in msg for s in ("503", "UNAVAILABLE", "overload", "high demand", "429")):
                        await asyncio.sleep(AI_RETRY_BASE_SECONDS * (attempt + 1))
                        continue
                    raise
            if response is None:
                raise last_err

            ai_response_text = response.text

            last_line = ai_response_text.strip().rsplit("\n", 1)[-1].strip().upper()
            risk_by_line = {
                "RISK: HIGH": models.RiskLevel.HIGH,
                "RISK: MODERATE": models.RiskLevel.MODERATE,
                "RISK: LOW": models.RiskLevel.LOW,
            }
            ai_risk_level = risk_by_line.get(last_line)
            if ai_risk_level is None:
                error_code = "AI_INVALID_RESPONSE"
                raise ValueError("Gemini response did not contain a valid risk line")
            assessment_status = "completed"
            error_code = None

        except asyncio.TimeoutError:
            logger.warning("Gemini timed out for pet_id=%s", pet_id)
            ai_response_text = None
            error_code = "AI_TIMEOUT"
        except Exception:
            logger.exception("Gemini analysis failed for pet_id=%s", pet_id)
            ai_response_text = None
            if error_code != "AI_INVALID_RESPONSE":
                error_code = "AI_UPSTREAM_ERROR"

    # Open the DB session only now that the slow work (Supabase upload + Gemini
    # call) is complete. The connection is held for <1s instead of 5-30s.
    with session_factory() as db:
        new_assessment = models.HealthAssessment(
            pet_id=pet_id,
            symptom_description=symptom_description,
            # Persist a stable object key. API responses generate an RLS-checked,
            # short-lived signed URL; a public URL must never be stored again.
            image_uri=unique_filename,
            risk_level=ai_risk_level,
            ai_raw_response=ai_response_text,
            status=assessment_status,
            error_code=error_code,
        )
        db.add(new_assessment)
        db.commit()
        db.refresh(new_assessment)
        # Detach so the caller can serialize the ORM object after the session
        # closes (FastAPI's response_model will read attributes off it).
        db.expunge(new_assessment)
        return _assessment_response(new_assessment, auth_context.access_token)
