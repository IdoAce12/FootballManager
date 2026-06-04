/** Pitch node coordinates (% left, % top) per formation slot index. */

export interface PitchNodeCoord {
  slotIndex: number;
  x: number;
  y: number;
}

export const FORMATION_NAMES = [
  '4-3-3',
  '4-4-2',
  '4-2-3-1',
  '3-5-2',
  '4-1-2-1-2',
  '5-3-2',
  '4-3-3 (False 9)',
] as const;

export type FormationName = (typeof FORMATION_NAMES)[number];

/** Slot layouts aligned with backend `FORMATIONS` slot order. */
export const FORMATION_LAYOUTS: Record<FormationName, PitchNodeCoord[]> = {
  '4-3-3': [
    { slotIndex: 0, x: 50, y: 88 },
    { slotIndex: 1, x: 86, y: 72 },
    { slotIndex: 2, x: 62, y: 74 },
    { slotIndex: 3, x: 38, y: 74 },
    { slotIndex: 4, x: 14, y: 72 },
    { slotIndex: 5, x: 68, y: 52 },
    { slotIndex: 6, x: 32, y: 52 },
    { slotIndex: 7, x: 50, y: 46 },
    { slotIndex: 8, x: 86, y: 24 },
    { slotIndex: 9, x: 50, y: 14 },
    { slotIndex: 10, x: 14, y: 24 },
  ],
  '4-4-2': [
    { slotIndex: 0, x: 50, y: 88 },
    { slotIndex: 1, x: 86, y: 72 },
    { slotIndex: 2, x: 62, y: 74 },
    { slotIndex: 3, x: 38, y: 74 },
    { slotIndex: 4, x: 14, y: 72 },
    { slotIndex: 5, x: 86, y: 48 },
    { slotIndex: 6, x: 62, y: 50 },
    { slotIndex: 7, x: 38, y: 50 },
    { slotIndex: 8, x: 14, y: 48 },
    { slotIndex: 9, x: 62, y: 18 },
    { slotIndex: 10, x: 38, y: 18 },
  ],
  '4-2-3-1': [
    { slotIndex: 0, x: 50, y: 88 },
    { slotIndex: 1, x: 86, y: 72 },
    { slotIndex: 2, x: 62, y: 74 },
    { slotIndex: 3, x: 38, y: 74 },
    { slotIndex: 4, x: 14, y: 72 },
    { slotIndex: 5, x: 62, y: 58 },
    { slotIndex: 6, x: 38, y: 58 },
    { slotIndex: 7, x: 50, y: 42 },
    { slotIndex: 8, x: 86, y: 28 },
    { slotIndex: 9, x: 14, y: 28 },
    { slotIndex: 10, x: 50, y: 14 },
  ],
  '3-5-2': [
    { slotIndex: 0, x: 50, y: 88 },
    { slotIndex: 1, x: 72, y: 74 },
    { slotIndex: 2, x: 50, y: 76 },
    { slotIndex: 3, x: 28, y: 74 },
    { slotIndex: 4, x: 90, y: 50 },
    { slotIndex: 5, x: 62, y: 52 },
    { slotIndex: 6, x: 50, y: 56 },
    { slotIndex: 7, x: 38, y: 52 },
    { slotIndex: 8, x: 10, y: 50 },
    { slotIndex: 9, x: 62, y: 18 },
    { slotIndex: 10, x: 38, y: 18 },
  ],
  '4-1-2-1-2': [
    { slotIndex: 0, x: 50, y: 88 },
    { slotIndex: 1, x: 86, y: 72 },
    { slotIndex: 2, x: 62, y: 74 },
    { slotIndex: 3, x: 38, y: 74 },
    { slotIndex: 4, x: 14, y: 72 },
    { slotIndex: 5, x: 50, y: 60 },
    { slotIndex: 6, x: 68, y: 48 },
    { slotIndex: 7, x: 32, y: 48 },
    { slotIndex: 8, x: 50, y: 36 },
    { slotIndex: 9, x: 62, y: 16 },
    { slotIndex: 10, x: 38, y: 16 },
  ],
  '5-3-2': [
    { slotIndex: 0, x: 50, y: 88 },
    { slotIndex: 1, x: 92, y: 68 },
    { slotIndex: 2, x: 68, y: 74 },
    { slotIndex: 3, x: 50, y: 76 },
    { slotIndex: 4, x: 32, y: 74 },
    { slotIndex: 5, x: 8, y: 68 },
    { slotIndex: 6, x: 68, y: 50 },
    { slotIndex: 7, x: 50, y: 52 },
    { slotIndex: 8, x: 32, y: 50 },
    { slotIndex: 9, x: 62, y: 18 },
    { slotIndex: 10, x: 38, y: 18 },
  ],
  '4-3-3 (False 9)': [
    { slotIndex: 0, x: 50, y: 88 },
    { slotIndex: 1, x: 86, y: 72 },
    { slotIndex: 2, x: 62, y: 74 },
    { slotIndex: 3, x: 38, y: 74 },
    { slotIndex: 4, x: 14, y: 72 },
    { slotIndex: 5, x: 50, y: 56 },
    { slotIndex: 6, x: 68, y: 50 },
    { slotIndex: 7, x: 32, y: 50 },
    { slotIndex: 8, x: 86, y: 24 },
    { slotIndex: 9, x: 50, y: 28 },
    { slotIndex: 10, x: 14, y: 24 },
  ],
};

export function layoutForFormation(name: string): PitchNodeCoord[] {
  return FORMATION_LAYOUTS[name as FormationName] ?? FORMATION_LAYOUTS['4-3-3'];
}
