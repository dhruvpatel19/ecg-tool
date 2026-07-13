from __future__ import annotations

import pytest

from app.coordinates import ViewerGeometry, point_to_ecg_coordinate


def test_point_to_ecg_coordinate_maps_lead_time_and_amplitude() -> None:
    geometry = ViewerGeometry(width=1200, height=900, time_start_sec=0, time_end_sec=10, amp_min_mv=-2, amp_max_mv=2)

    result = point_to_ecg_coordinate(450, 450, geometry)

    assert result["lead"] == "aVL"
    assert result["timeSec"] == 5
    assert result["amplitudeMv"] == 0


def test_point_to_ecg_coordinate_rejects_out_of_bounds() -> None:
    with pytest.raises(ValueError):
        point_to_ecg_coordinate(-1, 100, ViewerGeometry(width=1000, height=600))
