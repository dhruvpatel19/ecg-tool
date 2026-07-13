from __future__ import annotations

from dataclasses import dataclass

from .schemas import LEADS


LEAD_LAYOUT = [
    ["I", "aVR", "V1", "V4"],
    ["II", "aVL", "V2", "V5"],
    ["III", "aVF", "V3", "V6"],
]


@dataclass(frozen=True)
class ViewerGeometry:
    width: float
    height: float
    time_start_sec: float = 0.0
    time_end_sec: float = 10.0
    amp_min_mv: float = -2.0
    amp_max_mv: float = 2.0
    columns: int = 4
    rows: int = 3


def point_to_ecg_coordinate(x: float, y: float, geometry: ViewerGeometry) -> dict[str, float | str]:
    if geometry.width <= 0 or geometry.height <= 0:
        raise ValueError("Viewer geometry must have positive width and height")
    if x < 0 or y < 0 or x > geometry.width or y > geometry.height:
        raise ValueError("Point is outside viewer bounds")

    cell_w = geometry.width / geometry.columns
    cell_h = geometry.height / geometry.rows
    column = min(int(x / cell_w), geometry.columns - 1)
    row = min(int(y / cell_h), geometry.rows - 1)
    lead = LEAD_LAYOUT[row][column]

    local_x = x - column * cell_w
    local_y = y - row * cell_h
    time_range = geometry.time_end_sec - geometry.time_start_sec
    amp_range = geometry.amp_max_mv - geometry.amp_min_mv
    time_sec = geometry.time_start_sec + (local_x / cell_w) * time_range
    amplitude_mv = geometry.amp_max_mv - (local_y / cell_h) * amp_range

    return {
        "lead": lead,
        "timeSec": round(time_sec, 3),
        "amplitudeMv": round(amplitude_mv, 3),
    }


def clamp_action_to_case(action: dict, duration_sec: float, available_leads: list[str] | None = None) -> dict | None:
    available = set(available_leads or LEADS)
    lead = action.get("lead")
    leads = action.get("leads")
    if lead is not None and lead not in available:
        return None
    if leads is not None:
        filtered = [item for item in leads if item in available]
        if not filtered:
            return None
        action = {**action, "leads": filtered}
    for key in ("timeStart", "timeEnd", "timeSec"):
        if key in action and action[key] is not None:
            action[key] = max(0.0, min(float(action[key]), duration_sec))
    if action.get("timeStart") is not None and action.get("timeEnd") is not None:
        if action["timeEnd"] <= action["timeStart"]:
            return None
    return action
