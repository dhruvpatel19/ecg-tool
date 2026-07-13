export const leadLayout = [
  ["I", "aVR", "V1", "V4"],
  ["II", "aVL", "V2", "V5"],
  ["III", "aVF", "V3", "V6"],
] as const;

export type ECGPoint = {
  lead: string;
  timeSec: number;
  amplitudeMv: number;
};

/**
 * Map a point in the standard diagnostic print layout:
 *
 *   I   | aVR | V1 | V4
 *   II  | aVL | V2 | V5
 *   III | aVF | V3 | V6
 *   II rhythm strip (the full visible time window)
 *
 * The first three rows are sequential: each column owns one quarter of the
 * visible time window. Amplitude is derived from the same mm scale as the
 * renderer, so changing the digital zoom preserves square paper boxes and the
 * stated 25 mm/s, 10 mm/mV calibration.
 */
export function mapPointToStandardEcgCoordinate(
  x: number,
  y: number,
  width: number,
  height: number,
  timeStartSec = 0,
  timeEndSec = 10,
  paperSpeedMmPerSec = 25,
  gainMmPerMv = 10,
): ECGPoint {
  if (width <= 0 || height <= 0 || paperSpeedMmPerSec <= 0 || gainMmPerMv <= 0) {
    throw new Error("Viewer geometry and calibration must be positive");
  }
  if (timeEndSec <= timeStartSec) {
    throw new Error("Viewer time window must be positive");
  }
  if (x < 0 || y < 0 || x > width || y > height) {
    throw new Error("Point outside viewer");
  }

  const columns = 4;
  const rows = 4;
  const cellW = width / columns;
  const cellH = height / rows;
  const row = Math.min(Math.floor(y / cellH), rows - 1);
  const localY = y - row * cellH;
  const spanSec = timeEndSec - timeStartSec;
  const pxPerSec = width / spanSec;
  const pxPerMm = pxPerSec / paperSpeedMmPerSec;
  const pxPerMv = gainMmPerMv * pxPerMm;
  const amplitudeMv = (cellH / 2 - localY) / pxPerMv;

  if (row === rows - 1) {
    return {
      lead: "II",
      timeSec: Number((timeStartSec + x / pxPerSec).toFixed(3)),
      amplitudeMv: Number(amplitudeMv.toFixed(3)),
    };
  }

  const column = Math.min(Math.floor(x / cellW), columns - 1);
  const localX = x - column * cellW;
  const segmentSec = spanSec / columns;
  return {
    lead: leadLayout[row][column],
    timeSec: Number((timeStartSec + column * segmentSec + localX / pxPerSec).toFixed(3)),
    amplitudeMv: Number(amplitudeMv.toFixed(3)),
  };
}

export function mapPointToEcgCoordinate(
  x: number,
  y: number,
  width: number,
  height: number,
  timeStartSec = 0,
  timeEndSec = 10,
  ampMinMv = -2,
  ampMaxMv = 2,
): ECGPoint {
  if (width <= 0 || height <= 0) {
    throw new Error("Viewer geometry must be positive");
  }
  if (x < 0 || y < 0 || x > width || y > height) {
    throw new Error("Point outside viewer");
  }
  const columns = 4;
  const rows = 3;
  const cellW = width / columns;
  const cellH = height / rows;
  const column = Math.min(Math.floor(x / cellW), columns - 1);
  const row = Math.min(Math.floor(y / cellH), rows - 1);
  const localX = x - column * cellW;
  const localY = y - row * cellH;
  const timeSec = timeStartSec + (localX / cellW) * (timeEndSec - timeStartSec);
  const amplitudeMv = ampMaxMv - (localY / cellH) * (ampMaxMv - ampMinMv);
  return {
    lead: leadLayout[row][column],
    timeSec: Number(timeSec.toFixed(3)),
    amplitudeMv: Number(amplitudeMv.toFixed(3)),
  };
}

export function conceptLabel(id: string): string {
  const acronyms: Record<string, string> = {
    av: "AV",
    ecg: "ECG",
    mi: "MI",
    pr: "PR",
    qrs: "QRS",
    qt: "QT",
    qtc: "QTc",
    r: "R",
    rr: "R-R",
    st: "ST",
    t: "T",
  };
  return id
    .split("_")
    .map((part) => acronyms[part.toLowerCase()] ?? part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ")
    .replaceAll("R Wave", "R-Wave")
    .replaceAll("ST T", "ST-T");
}
