const leadLayout = [
  ["I", "aVR", "V1", "V4"],
  ["II", "aVL", "V2", "V5"],
  ["III", "aVF", "V3", "V6"],
];

function mapPointToEcgCoordinate(x, y, width, height, timeStartSec = 0, timeEndSec = 10, ampMinMv = -2, ampMaxMv = 2) {
  if (width <= 0 || height <= 0) throw new Error("bad geometry");
  if (x < 0 || y < 0 || x > width || y > height) throw new Error("outside");
  const cellW = width / 4;
  const cellH = height / 3;
  const column = Math.min(Math.floor(x / cellW), 3);
  const row = Math.min(Math.floor(y / cellH), 2);
  return {
    lead: leadLayout[row][column],
    timeSec: Number((timeStartSec + ((x - column * cellW) / cellW) * (timeEndSec - timeStartSec)).toFixed(3)),
    amplitudeMv: Number((ampMaxMv - ((y - row * cellH) / cellH) * (ampMaxMv - ampMinMv)).toFixed(3)),
  };
}

function mapPointToStandardEcgCoordinate(
  x,
  y,
  width,
  height,
  timeStartSec = 0,
  timeEndSec = 10,
  paperSpeedMmPerSec = 25,
  gainMmPerMv = 10,
) {
  if (width <= 0 || height <= 0 || paperSpeedMmPerSec <= 0 || gainMmPerMv <= 0) throw new Error("bad geometry");
  if (timeEndSec <= timeStartSec) throw new Error("bad time window");
  if (x < 0 || y < 0 || x > width || y > height) throw new Error("outside");
  const cellW = width / 4;
  const cellH = height / 4;
  const row = Math.min(Math.floor(y / cellH), 3);
  const localY = y - row * cellH;
  const span = timeEndSec - timeStartSec;
  const pxPerSec = width / span;
  const pxPerMm = pxPerSec / paperSpeedMmPerSec;
  const amplitudeMv = (cellH / 2 - localY) / (gainMmPerMv * pxPerMm);
  if (row === 3) {
    return {
      lead: "II",
      timeSec: Number((timeStartSec + x / pxPerSec).toFixed(3)),
      amplitudeMv: Number(amplitudeMv.toFixed(3)),
    };
  }
  const column = Math.min(Math.floor(x / cellW), 3);
  const localX = x - column * cellW;
  return {
    lead: leadLayout[row][column],
    timeSec: Number((timeStartSec + column * span / 4 + localX / pxPerSec).toFixed(3)),
    amplitudeMv: Number(amplitudeMv.toFixed(3)),
  };
}

const mapped = mapPointToEcgCoordinate(450, 450, 1200, 900);
if (mapped.lead !== "aVL" || mapped.timeSec !== 5 || mapped.amplitudeMv !== 0) {
  console.error(mapped);
  process.exit(1);
}

const standardLead = mapPointToStandardEcgCoordinate(450, 288, 1200, 768);
if (standardLead.lead !== "aVL" || standardLead.timeSec !== 3.75 || standardLead.amplitudeMv !== 0) {
  console.error(standardLead);
  process.exit(1);
}
const oneMv = mapPointToStandardEcgCoordinate(150, 48, 1200, 768);
if (oneMv.lead !== "I" || oneMv.timeSec !== 1.25 || oneMv.amplitudeMv !== 1) {
  console.error(oneMv);
  process.exit(1);
}
const rhythm = mapPointToStandardEcgCoordinate(600, 672, 1200, 768);
if (rhythm.lead !== "II" || rhythm.timeSec !== 5 || rhythm.amplitudeMv !== 0) {
  console.error(rhythm);
  process.exit(1);
}
const pxPerSec = 1200 / 10;
const pxPerMm = pxPerSec / 25;
const horizontalSmallBoxPx = 0.04 * pxPerSec;
const verticalSmallBoxPx = 0.1 * 10 * pxPerMm;
if (Math.abs(horizontalSmallBoxPx - verticalSmallBoxPx) > 1e-9) {
  console.error({ horizontalSmallBoxPx, verticalSmallBoxPx });
  process.exit(1);
}
console.log("frontend coordinate mapping ok (legacy grid + standard sequential/rhythm layout)");
