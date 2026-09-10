"""Pure telemetry state transitions; alerts are safety signals, never diagnoses."""
from dataclasses import dataclass
from datetime import datetime, timedelta
from math import asin, cos, radians, sin, sqrt
from typing import Optional

OFFLINE_AFTER = timedelta(minutes=10)
STATIONARY_AFTER = timedelta(hours=2)
MOVE_DISTANCE_M = 15.0
HIGH_SPEED_KMH = 35.0
HIGH_SPEED_SAMPLES = 3
LOW_BATTERY_PERCENT = 20


@dataclass(frozen=True)
class Detection:
    kind: str
    severity: str
    message: str
    metadata: dict


def distance_m(a_lat: float, a_lng: float, b_lat: float, b_lng: float) -> float:
    dlat, dlng = radians(b_lat - a_lat), radians(b_lng - a_lng)
    value = sin(dlat / 2) ** 2 + cos(radians(a_lat)) * cos(radians(b_lat)) * sin(dlng / 2) ** 2
    return 6371000 * 2 * asin(sqrt(value))


def _elapsed(later: datetime, earlier: datetime) -> timedelta:
    if later.tzinfo is not None and earlier.tzinfo is None:
        earlier = earlier.replace(tzinfo=later.tzinfo)
    elif later.tzinfo is None and earlier.tzinfo is not None:
        later = later.replace(tzinfo=earlier.tzinfo)
    return later - earlier


def offline_detection(last_seen_at: Optional[datetime], now: datetime) -> Optional[Detection]:
    if last_seen_at and _elapsed(now, last_seen_at) >= OFFLINE_AFTER:
        return Detection("device_offline", "warning", "The tracking device has stopped reporting. Please check the device.", {})
    return None


def apply_sample(*, device, lat: float, lng: float, speed_kmh: Optional[float], accuracy_m: Optional[float], recorded_at: datetime) -> list[Detection]:
    detections: list[Detection] = []
    moved = device.last_lat is None or distance_m(device.last_lat, device.last_lng, lat, lng) >= MOVE_DISTANCE_M
    if moved:
        device.last_moved_at = recorded_at
        device.motion_state = "moving"
    elif device.last_moved_at and _elapsed(recorded_at, device.last_moved_at) >= STATIONARY_AFTER:
        device.motion_state = "stationary"
        detections.append(Detection("prolonged_inactivity", "warning", "Little movement has been detected for an extended period. This is not a health diagnosis.", {}))
    else:
        device.motion_state = "stationary"
    if speed_kmh is not None and speed_kmh > HIGH_SPEED_KMH:
        device.high_speed_sample_count = (device.high_speed_sample_count or 0) + 1
        device.high_speed_started_at = device.high_speed_started_at or recorded_at
        if device.high_speed_sample_count >= HIGH_SPEED_SAMPLES:
            detections.append(Detection("sustained_high_speed", "warning", "Sustained high speed detected. Please verify the collar is secure; this is not a health diagnosis.", {"speed_kmh": speed_kmh}))
    else:
        device.high_speed_sample_count = 0
        device.high_speed_started_at = None
    device.last_lat, device.last_lng = lat, lng
    device.last_speed_kmh, device.last_accuracy_m = speed_kmh, accuracy_m
    device.last_seen_at = recorded_at
    return detections


def low_battery_detection(percent: Optional[int]) -> Optional[Detection]:
    if percent is not None and percent <= LOW_BATTERY_PERCENT:
        return Detection("low_battery", "warning", "Tracking device battery is low.", {"battery_percent": percent})
    return None
