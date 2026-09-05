// ─────────────────────────────────────────────
// Ditto DTCG Token Export — Atmosphere Handler
// Specialized processing for the 6 atmosphere tokens:
//   - 3 runtime parameters (hue-shift, chroma-boost, lightness-shift)
//   - 1 duration (breathe-duration)
//   - 2 calc-composite colors (surface-app-atmosphere, dark + light)
// ─────────────────────────────────────────────

import type { DtcgToken, RawCssToken, DittoExtensionMeta } from "./types";
import { oklchToHex } from "./oklch-converter";

// ── Token Name Constants ─────────────────────

const RUNTIME_PARAMS = new Set([
  "atmosphere-hue-shift",
  "atmosphere-chroma-boost",
  "atmosphere-lightness-shift",
]);

const CALC_COMPOSITE = "surface-app-atmosphere";
const DURATION_TOKEN = "atmosphere-breathe-duration";

// ── Regex Patterns ───────────────────────────

/**
 * Matches `calc(<number>` inside an `oklch(...)` value.
 * Each match captures the base numeric value before the `+` operator.
 *
 * Example input:
 *   "oklch(calc(0.166 + var(--atmosphere-lightness-shift)) calc(0.010 + var(--atmosphere-chroma-boost)) calc(253 + var(--atmosphere-hue-shift)))"
 *
 * Three matches: "0.166", "0.010", "253"
 */
const CALC_BASE_RE = /calc\(([\d.]+)/g;

// ── Public API ───────────────────────────────

/**
 * Check whether a raw CSS token belongs to the atmosphere layer.
 *
 * @param token - A parsed raw CSS token.
 * @returns `true` if the token's layer is "atmosphere".
 */
export function isAtmosphereToken(token: RawCssToken): boolean {
  return token.layer === "atmosphere";
}

/**
 * Extract base numeric values from a `calc()` expression inside `oklch()`.
 *
 * Parses the three `calc(<base> + var(...))` components and returns
 * the base values as `{ l, c, h }`. Returns `null` if extraction fails.
 *
 * @param rawValue - The full `oklch(calc(...))` value string.
 * @returns Object with `l`, `c`, `h` as numbers, or `null` on failure.
 */
export function extractCalcBaseValues(
  rawValue: string,
): { l: number; c: number; h: number } | null {
  const matches: string[] = [];

  CALC_BASE_RE.lastIndex = 0;
  let match: RegExpExecArray | null;
  while ((match = CALC_BASE_RE.exec(rawValue)) !== null) {
    const captured = match[1];
    if (captured !== undefined) matches.push(captured);
  }

  if (matches.length !== 3) {
    return null;
  }

  const [lRaw, cRaw, hRaw] = matches;
  if (lRaw === undefined || cRaw === undefined || hRaw === undefined) return null;
  const l = parseFloat(lRaw);
  const c = parseFloat(cRaw);
  const h = parseFloat(hRaw);

  if (Number.isNaN(l) || Number.isNaN(c) || Number.isNaN(h)) {
    return null;
  }

  return { l, c, h };
}

/**
 * Process all atmosphere-layer tokens into DTCG format.
 *
 * Handles three categories:
 *   1. Runtime parameters (number) — `dynamic: true`
 *   2. Duration (duration) — normal treatment
 *   3. Calc-composite colors — `runtimeDynamic: true` with fallback hex + `rawCss`
 *
 * @param tokens - Flat array of all parsed raw CSS tokens.
 * @returns Map keyed by token name, with context-qualified keys for
 *          theme-variant tokens (e.g. `"surface-app-atmosphere:light"`).
 */
export function processAtmosphereTokens(
  tokens: RawCssToken[],
): Map<string, DtcgToken> {
  const result = new Map<string, DtcgToken>();

  const atmosphereTokens = tokens.filter(isAtmosphereToken);

  for (const token of atmosphereTokens) {
    const dtcgToken = buildDtcgToken(token);
    if (!dtcgToken) continue;

    // Theme-variant tokens get a context-qualified key.
    // Default context tokens use their plain name.
    const key = token.context === "default"
      ? token.name
      : `${token.name}:${token.context}`;

    result.set(key, dtcgToken);
  }

  return result;
}

// ── Internal Helpers ─────────────────────────

/**
 * Build a DTCG token from a raw atmosphere token.
 *
 * Dispatches to the appropriate builder based on the token name.
 */
function buildDtcgToken(token: RawCssToken): DtcgToken | null {
  if (RUNTIME_PARAMS.has(token.name)) {
    return buildRuntimeParam(token);
  }

  if (token.name === CALC_COMPOSITE) {
    return buildCalcComposite(token);
  }

  if (token.name === DURATION_TOKEN) {
    return buildDuration(token);
  }

  // Unknown atmosphere token — skip.
  return null;
}

/**
 * Build a DTCG token for a runtime parameter.
 *
 * These are numeric values set by JS at runtime (e.g. `--atmosphere-hue-shift: 0`).
 * `$type` is "number", `$value` is the numeric string.
 */
function buildRuntimeParam(token: RawCssToken): DtcgToken {
  const extension: DittoExtensionMeta = {
    dynamic: true,
    source: token.sourceFile,
    layer: "atmosphere",
  };

  return {
    $value: token.value,
    $type: "number",
    $extensions: {
      "com.ditto-app": extension,
    },
  };
}

/**
 * Build a DTCG token for a duration value.
 *
 * Normal treatment — no special dynamic flags.
 */
function buildDuration(token: RawCssToken): DtcgToken {
  const extension: DittoExtensionMeta = {
    source: token.sourceFile,
    layer: "atmosphere",
  };

  return {
    $value: token.value,
    $type: "duration",
    $extensions: {
      "com.ditto-app": extension,
    },
  };
}

/**
 * Build a DTCG token for a calc-composite atmosphere color.
 *
 * The `$value` is the fallback hex (computed from base oklch values,
 * ignoring the `var()` offsets). The original `calc()` expression is
 * preserved in `$extensions.rawCss`.
 *
 * Example:
 *   Input:  `oklch(calc(0.166 + var(...)) calc(0.010 + var(...)) calc(253 + var(...)))`
 *   $value: `"#28282e"` (from oklch(0.166 0.010 253))
 *   rawCss: the full oklch(calc(...)) string
 */
function buildCalcComposite(token: RawCssToken): DtcgToken {
  const baseValues = extractCalcBaseValues(token.value);

  let fallbackHex: string;
  if (baseValues) {
    fallbackHex = oklchToHex(baseValues.l, baseValues.c, baseValues.h);
  } else {
    // Extraction failed — use a safe placeholder.
    // This should never happen with well-formed atmosphere tokens.
    fallbackHex = "#000000";
  }

  const extension: DittoExtensionMeta = {
    runtimeDynamic: true,
    rawCss: token.value,
    source: token.sourceFile,
    layer: "atmosphere",
  };

  return {
    $value: fallbackHex,
    $type: "color",
    $extensions: {
      "com.ditto-app": extension,
    },
  };
}
