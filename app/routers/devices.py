# -*- coding: utf-8 -*-
"""Feature 4 - Mode B: paired tracking devices (BLE/GPS collar).

Pairing + telemetry ingest. Telemetry is aggregated on arrival: only the
LATEST position is kept on the device row (live-map pin, SRS-F4-037/038);
the raw sample list is never persisted (proposal privacy rule). A finished
collar session may be flushed into activity_logs with source='device'.
"""
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app import models
from app.auth import get_current_user, require_owned_pet
from app.database import get_db
from app.services.anomaly import detect_anomalies
from app.utils.time import now_bkk

router = APIRouter(prefix="/api/v1", tags=["Tracking Devices"])


# ==========================================
# Schemas
# ==========================================
class DevicePair(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    identifier: str = Field(min_length=3, max_length=120)  # MAC address / serial
    device_type: str = "ble_collar"


class DeviceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    pet_id: int
    name: str
    device_type: str
    identifier: str
    is_active: bool
    battery_percent: Optional[int] = None
    last_lat: Optional[float] = None
    last_lng: Optional[float] = None
    last_seen_at: Optional[datetime] = None
    paired_at: Optional[datetime] = None



class TelemetrySample(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    speed_kmh: Optional[float] = Field(default=None, ge=0, le=500)
    recorded_at: Optional[datetime] = None


class TelemetryBatch(BaseModel):
    samples: List[TelemetrySample]
    battery_percent: Optional[int] = Field(default=None, ge=0, le=100)
    # When the collar reports a finished movement session, the aggregates are
    # written to activity_logs (source='device') so stats/missions see them.
    session_duration_minutes: Optional[float] = Field(default=None, ge=0)
    session_distance_meters: Optional[float] = Field(default=None, ge=0)


class TelemetryResult(BaseModel):
    device: DeviceResponse
    anomalies: List[dict]
    activity_logged: bool


def _require_owned_device(device_id: int, current_user: models.User, db: Session) -> models.Device:
    device = db.query(models.Device).filter(models.Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    require_owned_pet(device.pet_id, current_user, db)
    return device


# ==========================================
# Pairing
# ==========================================
@router.post("/pets/{pet_id}/devices", response_model=DeviceResponse)
def pair_device(
    pet_id: int,
    payload: DevicePair,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Pair a collar with a pet (SRS-F4-035)."""
    require_owned_pet(pet_id, current_user, db)

    existing = db.query(models.Device).filter(
        models.Device.identifier == payload.identifier
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="Device is already paired")

    device = models.Device(pet_id=pet_id, **payload.model_dump())
    db.add(device)
    db.commit()
    db.refresh(device)
    return device


@router.get("/pets/{pet_id}/devices", response_model=List[DeviceResponse])
def list_devices(
    pet_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owned_pet(pet_id, current_user, db)
    return db.query(models.Device).filter(models.Device.pet_id == pet_id).all()


@router.delete("/devices/{device_id}")
def unpair_device(
    device_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    device = _require_owned_device(device_id, current_user, db)
    db.delete(device)
    db.commit()
    return {"message": "Device unpaired"}


# ==========================================
# Telemetry ingest
# ==========================================
@router.post("/devices/{device_id}/telemetry", response_model=TelemetryResult)
def ingest_telemetry(
    device_id: int,
    batch: TelemetryBatch,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Ingest a collar telemetry batch (SRS-F4-037..042).

    Aggregates in-memory: keeps only the latest position on the device row and
    optionally flushes a finished session into activity_logs. Raw samples are
    discarded after this request.
    """
    device = _require_owned_device(device_id, current_user, db)
    if not batch.samples:
        raise HTTPException(status_code=400, detail="Telemetry batch is empty")

    now = now_bkk()
    speeds = [s.speed_kmh for s in batch.samples if s.speed_kmh is not None]
    max_speed = max(speeds) if speeds else None

    # Anomaly rules run BEFORE last_seen_at is refreshed, so a long gap since
    # the previous batch is visible to the inactivity rule (SRS-F4-040).
    previous_seen = device.last_seen_at
    anomalies = detect_anomalies(
        last_seen_at=previous_seen, now=now, max_speed_kmh=max_speed,
    )

    latest = batch.samples[-1]
    device.last_lat = latest.lat
    device.last_lng = latest.lng
    device.last_seen_at = now
    if batch.battery_percent is not None:
        device.battery_percent = batch.battery_percent

    activity_logged = False
    if batch.session_duration_minutes and batch.session_duration_minutes > 0:
        db.add(models.ActivityLog(
            pet_id=device.pet_id,
            source=models.ActivitySource.DEVICE,
            activity_type="walking",
            duration_minutes=batch.session_duration_minutes,
            distance_meters=batch.session_distance_meters or 0.0,
            max_speed_kmh=max_speed,
        ))
        activity_logged = True

    db.commit()
    db.refresh(device)

    return TelemetryResult(
        device=DeviceResponse.model_validate(device),
        anomalies=[{"kind": a.kind, "message": a.message} for a in anomalies],
        activity_logged=activity_logged,
    )
