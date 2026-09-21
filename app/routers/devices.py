"""Owner-scoped device pairing, telemetry, persistent alerts and sessions."""
from datetime import datetime, timedelta
from typing import List, Optional
from uuid import UUID
import hashlib

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app import models
from app.auth import get_current_user, require_owned_pet
from app.database import get_db
from app.routers.activities import _complete_walk_mission
from app.services.anomaly import (
    apply_sample,
    distance_m,
    low_battery_detection,
    offline_detection,
)
from app.utils.time import now_bkk

router = APIRouter(prefix="/api/v1", tags=["Tracking Devices"])


class DevicePair(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    identifier: str = Field(min_length=3, max_length=120)
    device_type: str = "ble_collar"


class DeviceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; pet_id: int; name: str; device_type: str; identifier: str; is_active: bool
    battery_percent: Optional[int] = None
    last_lat: Optional[float] = None; last_lng: Optional[float] = None
    last_seen_at: Optional[datetime] = None; paired_at: Optional[datetime] = None
    last_speed_kmh: Optional[float] = None; last_accuracy_m: Optional[float] = None
    last_moved_at: Optional[datetime] = None; motion_state: str = "unknown"


class AlertResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; device_id: int; alert_type: str; severity: str; message: str
    detected_at: datetime; acknowledged_at: Optional[datetime] = None; resolved_at: Optional[datetime] = None
    alert_metadata: dict = Field(validation_alias="alert_metadata", serialization_alias="metadata")


class TelemetrySample(BaseModel):
    lat: float = Field(ge=-90, le=90); lng: float = Field(ge=-180, le=180)
    speed_kmh: Optional[float] = Field(default=None, ge=0, le=200)
    accuracy_m: Optional[float] = Field(default=None, ge=0, le=10000)
    recorded_at: Optional[datetime] = None


class TelemetryBatch(BaseModel):
    samples: List[TelemetrySample] = Field(min_length=1, max_length=500)
    battery_percent: Optional[int] = Field(default=None, ge=0, le=100)
    session_id: Optional[UUID] = None
    session_duration_minutes: Optional[float] = Field(default=None, ge=0, le=1440)
    session_distance_meters: Optional[float] = Field(default=None, ge=0, le=1000000)


class TelemetryResult(BaseModel):
    device: DeviceResponse; anomalies: List[dict]; activity_logged: bool


class TelemetryPointResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    device_id: int
    lat: float
    lng: float
    speed_kmh: Optional[float] = None
    accuracy_m: Optional[float] = None
    motion_state: str
    recorded_at: datetime


class MotionSummaryResponse(BaseModel):
    sample_count: int
    moving_minutes: float
    stationary_minutes: float
    distance_meters: float
    average_speed_kmh: float
    maximum_speed_kmh: float
    trend: str
    window_hours: int


def _owned_device(device_id: int, user: models.User, db: Session) -> models.Device:
    device = db.query(models.Device).filter_by(id=device_id).first()
    if not device: raise HTTPException(404, "Device not found")
    require_owned_pet(device.pet_id, user, db)
    return device


def _persist(db: Session, device: models.Device, detection):
    active = db.query(models.DeviceAlert).filter_by(device_id=device.id, alert_type=detection.kind, resolved_at=None).first()
    if active: return active
    alert = models.DeviceAlert(device_id=device.id, alert_type=detection.kind, severity=detection.severity, message=detection.message, alert_metadata=detection.metadata)
    db.add(alert); return alert


@router.post("/pets/{pet_id}/devices", response_model=DeviceResponse)
def pair_device(pet_id: int, payload: DevicePair, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    require_owned_pet(pet_id, user, db)
    if db.query(models.Device).filter_by(identifier=payload.identifier).first(): raise HTTPException(409, "Device is already paired")
    row = models.Device(pet_id=pet_id, **payload.model_dump()); db.add(row); db.commit(); db.refresh(row); return row


@router.get("/pets/{pet_id}/devices", response_model=List[DeviceResponse])
def list_devices(pet_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    require_owned_pet(pet_id, user, db); return db.query(models.Device).filter_by(pet_id=pet_id).all()


@router.delete("/devices/{device_id}")
def unpair_device(device_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    row = _owned_device(device_id, user, db); db.delete(row); db.commit(); return {"message": "Device unpaired"}


@router.post("/devices/{device_id}/telemetry", response_model=TelemetryResult)
def ingest_telemetry(device_id: int, batch: TelemetryBatch, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    device = _owned_device(device_id, user, db); now = now_bkk(); found = []
    for sample in sorted(batch.samples, key=lambda x: x.recorded_at or now):
        stamp = sample.recorded_at or now
        if stamp > now + timedelta(minutes=5) or stamp < now - timedelta(days=7): raise HTTPException(422, "Telemetry timestamp is outside the accepted window")
        found += apply_sample(device=device, lat=sample.lat, lng=sample.lng, speed_kmh=sample.speed_kmh, accuracy_m=sample.accuracy_m, recorded_at=stamp)
        db.add(models.DeviceTelemetryPoint(
            device_id=device.id,
            lat=sample.lat,
            lng=sample.lng,
            speed_kmh=sample.speed_kmh,
            accuracy_m=sample.accuracy_m,
            motion_state=device.motion_state,
            recorded_at=stamp,
        ))
    if batch.battery_percent is not None: device.battery_percent = batch.battery_percent
    battery = low_battery_detection(batch.battery_percent)
    if battery: found.append(battery)
    for detection in found: _persist(db, device, detection)
    activity_logged = False
    if batch.session_duration_minutes and batch.session_duration_minutes > 0:
        if batch.session_id:
            key = f"tracking:{batch.session_id}"
        else:
            fingerprint = f"{device.id}:{batch.session_duration_minutes}:{batch.session_distance_meters}:{[(s.lat, s.lng, s.recorded_at) for s in batch.samples]}"
            key = "tracking:auto:" + hashlib.sha256(fingerprint.encode()).hexdigest()
        existing = db.query(models.ActivityLog).filter_by(pet_id=device.pet_id, session_key=key).first()
        if not existing:
            qualifies = batch.session_duration_minutes >= 15
            db.add(models.ActivityLog(pet_id=device.pet_id, source=models.ActivitySource.DEVICE, activity_type="walking", duration_minutes=batch.session_duration_minutes, distance_meters=batch.session_distance_meters or 0, max_speed_kmh=max((s.speed_kmh or 0 for s in batch.samples), default=0), session_key=key, is_mission_completed=qualifies))
            if qualifies: _complete_walk_mission(device.pet_id, db)
            activity_logged = True
    db.query(models.DeviceTelemetryPoint).filter(
        models.DeviceTelemetryPoint.device_id == device.id,
        models.DeviceTelemetryPoint.recorded_at < now - timedelta(days=7),
    ).delete(synchronize_session=False)
    db.commit(); db.refresh(device)
    return TelemetryResult(device=DeviceResponse.model_validate(device), anomalies=[{"kind": d.kind, "message": d.message} for d in found], activity_logged=activity_logged)


@router.get(
    "/devices/{device_id}/telemetry-history",
    response_model=List[TelemetryPointResponse],
)
def telemetry_history(
    device_id: int,
    minutes: int = Query(60, ge=5, le=10080),
    limit: int = Query(300, ge=1, le=1000),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    _owned_device(device_id, user, db)
    cutoff = now_bkk() - timedelta(minutes=minutes)
    newest_first = (
        db.query(models.DeviceTelemetryPoint)
        .filter(
            models.DeviceTelemetryPoint.device_id == device_id,
            models.DeviceTelemetryPoint.recorded_at >= cutoff,
        )
        .order_by(models.DeviceTelemetryPoint.recorded_at.desc())
        .limit(limit)
        .all()
    )
    return list(reversed(newest_first))


@router.get(
    "/devices/{device_id}/motion-summary",
    response_model=MotionSummaryResponse,
)
def motion_summary(
    device_id: int,
    hours: int = Query(24, ge=1, le=168),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    _owned_device(device_id, user, db)
    cutoff = now_bkk() - timedelta(hours=hours)
    points = (
        db.query(models.DeviceTelemetryPoint)
        .filter(
            models.DeviceTelemetryPoint.device_id == device_id,
            models.DeviceTelemetryPoint.recorded_at >= cutoff,
        )
        .order_by(models.DeviceTelemetryPoint.recorded_at.asc())
        .all()
    )
    moving_seconds = stationary_seconds = total_distance = 0.0
    speeds = [point.speed_kmh for point in points if point.speed_kmh is not None]
    for previous, current in zip(points, points[1:]):
        delta = (current.recorded_at - previous.recorded_at).total_seconds()
        # A long reporting gap is not evidence that the pet stayed in the same
        # state. Count at most five minutes for each observed interval.
        observed_seconds = max(0.0, min(delta, 300.0))
        if previous.motion_state == "moving":
            moving_seconds += observed_seconds
        elif previous.motion_state == "stationary":
            stationary_seconds += observed_seconds
        segment_distance = distance_m(
            previous.lat,
            previous.lng,
            current.lat,
            current.lng,
        )
        # Ignore sub-meter GPS jitter and implausible jumps. Large gaps can be
        # caused by a stale fix or a reconnect and would otherwise inflate the
        # owner-facing distance trend.
        if 1.0 <= segment_distance <= 200.0:
            total_distance += segment_distance

    observed = moving_seconds + stationary_seconds
    if len(points) < 2 or observed == 0:
        trend = "insufficient_data"
    elif moving_seconds / observed >= 0.6:
        trend = "mostly_moving"
    elif stationary_seconds / observed >= 0.6:
        trend = "mostly_stationary"
    else:
        trend = "mixed"
    return MotionSummaryResponse(
        sample_count=len(points),
        moving_minutes=round(moving_seconds / 60, 1),
        stationary_minutes=round(stationary_seconds / 60, 1),
        distance_meters=round(total_distance, 1),
        average_speed_kmh=round(sum(speeds) / len(speeds), 1) if speeds else 0,
        maximum_speed_kmh=round(max(speeds), 1) if speeds else 0,
        trend=trend,
        window_hours=hours,
    )


@router.get("/pets/{pet_id}/device-alerts", response_model=List[AlertResponse])
def list_alerts(pet_id: int, active_only: bool = Query(False), db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    require_owned_pet(pet_id, user, db)
    query = db.query(models.DeviceAlert).join(models.Device).filter(models.Device.pet_id == pet_id)
    if active_only: query = query.filter(models.DeviceAlert.resolved_at.is_(None))
    return query.order_by(models.DeviceAlert.detected_at.desc()).limit(100).all()


def _owned_alert(alert_id: int, user, db):
    alert = db.query(models.DeviceAlert).filter_by(id=alert_id).first()
    if not alert: raise HTTPException(404, "Alert not found")
    _owned_device(alert.device_id, user, db); return alert


@router.post("/device-alerts/{alert_id}/acknowledge", response_model=AlertResponse)
def acknowledge(alert_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    alert = _owned_alert(alert_id, user, db); alert.acknowledged_at = alert.acknowledged_at or now_bkk(); db.commit(); db.refresh(alert); return alert


@router.post("/device-alerts/{alert_id}/resolve", response_model=AlertResponse)
def resolve(alert_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    alert = _owned_alert(alert_id, user, db); alert.resolved_at = alert.resolved_at or now_bkk(); db.commit(); db.refresh(alert); return alert


@router.post("/devices/{device_id}/check-offline", response_model=List[AlertResponse])
def check_offline(device_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    device = _owned_device(device_id, user, db); detection = offline_detection(device.last_seen_at, now_bkk())
    if detection: device.motion_state = "offline"; _persist(db, device, detection)
    db.commit(); return db.query(models.DeviceAlert).filter_by(device_id=device.id, resolved_at=None).all()
