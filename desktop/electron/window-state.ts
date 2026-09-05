export type Bounds = { x: number; y: number; width: number; height: number };

/** Restore within a current display's usable area, including small screens. */
export function visibleWindowBounds(saved: Partial<Bounds>, displays: Bounds[]): Bounds {
  const primary = displays[0] || { x: 0, y: 0, width: 1180, height: 820 };
  const valid = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value);
  const x = valid(saved.x) ? saved.x : primary.x;
  const y = valid(saved.y) ? saved.y : primary.y;
  const display = displays.find(d => x >= d.x && x < d.x + d.width && y >= d.y && y < d.y + d.height) || primary;
  const width = Math.min(display.width, Math.max(900, valid(saved.width) ? saved.width : 1180));
  const height = Math.min(display.height, Math.max(640, valid(saved.height) ? saved.height : 820));
  return {
    width, height,
    x: Math.round(Math.max(display.x, Math.min(x, display.x + display.width - width))),
    y: Math.round(Math.max(display.y, Math.min(y, display.y + display.height - height))),
  };
}
