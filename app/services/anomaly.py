# -*- coding: utf-8 -*-
"""Anomaly detection for collar telemetry (SRS-F4-039..042) - Progress II skeleton.

Rules operate on the aggregate metrics of one telemetry batch, never on a
stored route (raw GPS is processed in-memory only, per the proposal privacy
rule). Detected anomalies are returned to the caller; wiring them to FCM push
is tracked separately (see fcm-integration-plan).
"""
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Optional

# Configurable thresholds (SRS-F4-040/041). Kept as module constants until a
# per-pet settings table exists.
INACTIVITY_THRESHOLD = timedelta(hours=2)
MAX_PLAUSIBLE_SPEED_KMH = 35.0  # above this the collar is likely in a vehicle / glitching


@dataclass
class Anomaly:
    kind: str      # "inactivity" | "abnormal_speed"
    message: str


def detect_anomalies(
    *,
    last_seen_at: Optional[datetime],
    now: datetime,
    max_speed_kmh: Optional[float],
) -> List[Anomaly]:
    """Evaluate the anomaly rules for one telemetry ingest."""
    anomalies: List[Anomaly] = []

    if last_seen_at is not None and (now - last_seen_at) >= INACTIVITY_THRESHOLD:
        hours = int((now - last_seen_at).total_seconds() // 3600)
        anomalies.append(Anomaly(
            kind="inactivity",
            message=f"Your pet has not moved for {hours} hours. Please check on them.",
        ))

    if max_speed_kmh is not None and max_speed_kmh > MAX_PLAUSIBLE_SPEED_KMH:
        anomalies.append(Anomaly(
            kind="abnormal_speed",
            message=(
                f"Abnormal movement speed detected ({max_speed_kmh:.0f} km/h). "
                "Please verify the collar is on your pet."
            ),
        ))

    # TODO(Progress II): push each anomaly to the owner via FCM (SRS-F4-042).
    return anomalies
