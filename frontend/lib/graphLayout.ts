// Fixed, readable layout for the causal graph (presentation only). Columns follow the four
// domains; the stock-flow block sits underneath; inputs (U, D) sit on the outer bands.

export const GRAPH_W = 1200;
export const GRAPH_H = 790;

export const NODE_POS: Record<string, [number, number]> = {
  // ENV
  E: [170, 170], F: [85, 285], O: [170, 360], M: [255, 285],
  // SOC
  C: [460, 170], J: [375, 285], H: [545, 285], T: [460, 360],
  // ORG
  A: [750, 170], K: [665, 300], L: [835, 300], R: [750, 400],
  // SUP
  S: [1040, 170], TR: [955, 285], IF: [1125, 285], P: [1040, 360],
  // stock-flow
  I: [300, 560], Q: [520, 560], C_flow: [740, 560], mu: [960, 560], Qp: [520, 670], flex: [740, 670],
  // interventions (top band)
  U_environment: [170, 50], U_access: [650, 50], U_coordination: [800, 50], U_capacity: [955, 50], U_training: [1060, 50], U_followthrough: [1160, 50],
  // external conditions (bottom band)
  resource_availability: [1080, 760], staff_turnover: [880, 760], academic_load: [300, 760],
};

export const DOMAIN_BANDS = [
  { id: "ENV", x: 30, w: 280 },
  { id: "SOC", x: 320, w: 280 },
  { id: "ORG", x: 610, w: 280 },
  { id: "SUP", x: 900, w: 280 },
];

export function edgePath(sx: number, sy: number, tx: number, ty: number, r = 22, bend = 0.18): string {
  const dx = tx - sx, dy = ty - sy;
  const len = Math.hypot(dx, dy) || 1;
  const ux = dx / len, uy = dy / len;
  const x1 = sx + ux * r, y1 = sy + uy * r;
  const x2 = tx - ux * (r + 4), y2 = ty - uy * (r + 4);
  const mx = (x1 + x2) / 2 - uy * len * bend, my = (y1 + y2) / 2 + ux * len * bend;
  return `M${x1.toFixed(1)},${y1.toFixed(1)} Q${mx.toFixed(1)},${my.toFixed(1)} ${x2.toFixed(1)},${y2.toFixed(1)}`;
}
