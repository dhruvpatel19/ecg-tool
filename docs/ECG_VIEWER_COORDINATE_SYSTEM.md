# ECG Viewer Coordinate System

## Layout

The viewer uses a 3 x 4 12-lead layout:

| Row | Leads |
| --- | --- |
| 1 | I, aVR, V1, V4 |
| 2 | II, aVL, V2, V5 |
| 3 | III, aVF, V3, V6 |

Each cell renders the selected time window for that lead. The default window is 0-10 seconds.

## Mapping

A click maps from SVG pixels to:

```json
{
  "lead": "II",
  "timeSec": 3.42,
  "amplitudeMv": 0.64
}
```

The backend endpoint `/viewer/map-point` and frontend `mapPointToEcgCoordinate` use the same calculation:

- determine the grid cell from x/y
- map local x to the active time window
- map local y to the configured amplitude range

The amplitude range is ±2.0 mV on both the backend (`coordinates.py`) and frontend (`coordinates.ts`).

## Calibrated grid

The grid is true ECG paper at **25 mm/s, 10 mm/mV**: minor lines every 0.04 s / 0.1 mV, major every 0.2 s / 0.5 mV, computed from the *current visible window* so box-counting stays valid through zoom/pan. A calibration label and pulse marker are shown.

## Interactions

- zoom / pan / reset view
- lead highlighting and ROI overlays (labels hidden by default; shown on hover or for the AI-highlighted ROI)
- calipers, click coordinate readout, drag annotation
- **click-to-grade** — "Identify feature" mode posts the clicked point to `/grade/click/{id}` and grades it against the lesson's target segment ROI (`noTarget` distinguishes "no target here" from a wrong click)
- **median-beat view** — toggles a clean 12-lead averaged complex
- AI viewer action execution (zoom/highlight/ROI/caliper/fiducial), clamped to the case bounds

Coordinate mapping is tested in backend pytest and frontend `npm run test:coords`.
