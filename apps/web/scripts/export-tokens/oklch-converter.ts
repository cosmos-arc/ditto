// ─────────────────────────────────────────────
// Ditto OKLCH Converter
// Standalone OKLCH ↔ Hex conversion powered by culori v4.
// Replaces the manual matrix math in token-utils.mjs.
// ─────────────────────────────────────────────

import {
  oklch as culoriOklch,
  parse as culoriParse,
  formatHex,
  formatHex8,
} from "culori";

// ── Culori v4 Type Declarations ──────────────
// culori@4.0.2 ships no TypeScript declarations.
// We define the minimum shapes we actually use.

interface CuloriOklchColor {
  mode: "oklch";
  l: number;
  c: number;
  h: number;
  alpha?: number;
}

interface CuloriColor {
  mode: string;
  [key: string]: unknown;
}

// ── Regex Patterns ───────────────────────────
// Lifted from token-utils.mjs — module-level constants, not inlined.

const OKLCH_RE =
  /oklch\(\s*([\d.]+%?)\s+([\d.]+)\s+([\d.]+)(?:\s*\/\s*([\d.]+))?\s*\)/;

const RELATIVE_OKLCH_RE =
  /oklch\(\s*from\s+var\(([^)]+)\)\s+([\w%]+)\s+([\w]+)\s+([\w]+)(?:\s*\/\s*([\d.]+))?\s*\)/;

// ── Helper: parse oklch string → components ──

export interface OklchComponents {
  l: number;
  c: number;
  h: number;
  alpha: number;
}

/**
 * Parse an oklch() string into numeric components.
 * Handles both `oklch(L C H)` and `oklch(L C H / alpha)`.
 * Returns `null` if the string doesn't match the oklch pattern.
 */
export function parseOklchString(value: string): OklchComponents | null {
  const trimmed = value.trim();
  const match = OKLCH_RE.exec(trimmed);
  if (!match) return null;

  const lRaw = match[1] as string;
  const l = lRaw.endsWith("%") ? parseFloat(lRaw) / 100 : parseFloat(lRaw);
  const c = parseFloat(match[2] as string);
  const h = parseFloat(match[3] as string);
  const alpha = match[4] !== undefined ? parseFloat(match[4] as string) : 1;

  return { l, c, h, alpha };
}

// ── Helper: type predicates ──────────────────

/** Check if a CSS value string is a standard oklch() color. */
export function isOklch(value: string): boolean {
  return OKLCH_RE.test(value.trim());
}

/** Check if a CSS value string uses relative oklch() syntax. */
export function isRelativeOklch(value: string): boolean {
  return RELATIVE_OKLCH_RE.test(value.trim());
}

// ── Core: oklch → Hex ────────────────────────

/**
 * Convert OKLCH components to a hex color string.
 *
 * @param l - Lightness (0–1)
 * @param c - Chroma (0–0.4)
 * @param h - Hue (0–360)
 * @param alpha - Optional alpha (0–1). When < 1, returns 8-digit hex (#rrggbbaa).
 * @returns Hex color string (`#rrggbb` or `#rrggbbaa`).
 */
export function oklchToHex(
  l: number,
  c: number,
  h: number,
  alpha?: number,
): string {
  const oklchInput: CuloriOklchColor = { mode: "oklch", l, c, h };
  if (alpha !== undefined && alpha < 1) {
    oklchInput.alpha = alpha;
  }

  const color = culoriOklch(oklchInput) as CuloriColor | undefined;
  if (!color) {
    throw new Error(
      `culori failed to convert oklch(${l} ${c} ${h}${alpha !== undefined ? ` / ${alpha}` : ""})`,
    );
  }

  if (alpha !== undefined && alpha < 1) {
    return formatHex8(color) as string;
  }
  return formatHex(color) as string;
}

// ── Core: Hex → oklch ────────────────────────

export interface OklchResult {
  l: number;
  c: number;
  h: number;
}

/**
 * Parse a hex color string to OKLCH components.
 * Used for roundtrip verification (hex → oklch → hex).
 *
 * @param hex - Hex color string (e.g. `#2e97ca` or `#2e97ca80`).
 * @returns Object with `l`, `c`, `h` as numbers.
 */
export function hexToOklch(hex: string): OklchResult {
  const parsed = culoriParse(hex);
  if (!parsed) {
    throw new Error(`culori failed to parse hex color: ${hex}`);
  }

  const oklchColor = culoriOklch(parsed) as CuloriOklchColor | undefined;
  if (!oklchColor) {
    throw new Error(`culori failed to convert ${hex} to oklch`);
  }

  return {
    l: oklchColor.l,
    c: oklchColor.c,
    h: oklchColor.h,
  };
}

// ── Core: resolve relative oklch ─────────────

export interface ResolvedRelativeOklch {
  oklch: string;
  hex: string;
}

/**
 * Resolve a relative oklch() expression by applying a new alpha to a base oklch color.
 *
 * Example:
 *   baseOklchString = "oklch(0.640 0.120 235)"
 *   alpha = 0.10
 *   → { oklch: "oklch(0.640 0.120 235 / 0.1)", hex: "#2e97ca1a" }
 *
 * @param baseOklchString - The base token's oklch() value (without alpha override).
 * @param alpha - The alpha to apply (0–1).
 * @returns Both the oklch string and the hex equivalent.
 */
export function resolveRelativeOklch(
  baseOklchString: string,
  alpha: number,
): ResolvedRelativeOklch {
  const parsed = parseOklchString(baseOklchString);
  if (!parsed) {
    throw new Error(
      `Cannot parse base oklch string: ${baseOklchString}`,
    );
  }

  const { l, c, h } = parsed;

  // Build the oklch string with the new alpha
  const alphaStr =
    alpha < 1
      ? `oklch(${l} ${c} ${h} / ${alpha})`
      : `oklch(${l} ${c} ${h})`;

  const hex = oklchToHex(l, c, h, alpha);

  return { oklch: alphaStr, hex };
}
