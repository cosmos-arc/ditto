// ─────────────────────────────────────────────
// Ditto DTCG Token Export — Composite Builder
// Builds structured DTCG tokens from parsed composite values:
//   shadow, border, transition, and shorthand patterns.
// ─────────────────────────────────────────────

import { parseOklchString, oklchToHex, isOklch } from "./oklch-converter";

import type {
  ParsedValue,
  ParsedCompositeShadow,
  ParsedCompositeBorder,
  ParsedCompositeTransition,
  ParsedCompositeShorthand,
  DtcgToken,
  DtcgShadowValue,
  DtcgBorderValue,
  DtcgTransitionValue,
} from "./types";

// ── Type Predicate ───────────────────────────

const COMPOSITE_TYPES: readonly string[] = [
  "composite-shadow",
  "composite-border",
  "composite-transition",
  "composite-shorthand",
] as const;

/**
 * Returns true if the parsed value is any composite type
 * (shadow, border, transition, or shorthand).
 */
export function isComposite(parsedValue: ParsedValue): boolean {
  return (COMPOSITE_TYPES as readonly string[]).includes(parsedValue.type);
}

// ── Regex Patterns ───────────────────────────

/** Match `var(--name)` and return the name portion. */
const VAR_RE = /^var\(([^)]+)\)$/;

// ── Public API ───────────────────────────────

/**
 * Build a structured DTCG token from a parsed composite value.
 *
 * Returns `null` if the value is not a recognized composite type.
 * When a `var()` reference cannot be found in referenceMap, the raw
 * `var()` string is preserved as-is.
 *
 * @param tokenName    - The token name (e.g. "interaction-dragging-shadow").
 * @param parsedValue  - A parsed value from the reference resolver.
 * @param referenceMap - Token name → DTCG path mapping (from buildReferenceMap).
 */
export function buildCompositeValue(
  _tokenName: string,
  parsedValue: ParsedValue,
  referenceMap: Map<string, string>,
): DtcgToken | null {
  switch (parsedValue.type) {
    case "composite-shadow":
      return buildShadow(parsedValue);
    case "composite-border":
      return buildBorder(parsedValue, referenceMap);
    case "composite-transition":
      return buildTransition(parsedValue, referenceMap);
    case "composite-shorthand":
      return buildShorthand(parsedValue);
    default:
      return null;
  }
}

// ── Shadow Builder ───────────────────────────

/**
 * Build a DTCG shadow token from a composite-shadow parsed value.
 *
 * Expected input: `"0 8px 24px oklch(0 0 0 / 0.4)"`
 *
 * Tokenizes the raw string into offset-X, offset-Y, blur, and color parts.
 * Handles both `px` suffixed dimensions and bare numbers (defaulting to px).
 */
function buildShadow(parsed: ParsedCompositeShadow): DtcgToken {
  const parts = parsed.value.trim().split(/\s+/);

  // A valid shadow has at least 4 parts: offsetX, offsetY, blur, color.
  if (parts.length < 4) {
    return {
      $value: parsed.value,
      $type: "other",
      $extensions: {
        "com.ditto-app": {
          compositeType: "shadow",
          rawCss: `invalid shadow format: ${parsed.value}`,
        },
      },
    };
  }

  const rawOffsetX = parts[0] as string;
  const rawOffsetY = parts[1] as string;
  const rawBlur = parts[2] as string;
  const colorStr = parts.slice(3).join(" ");

  const offsetX = parseDimensionPart(rawOffsetX, "0");
  const offsetY = parseDimensionPart(rawOffsetY, "0");
  const blur = parseDimensionPart(rawBlur, "0");
  const color = convertColorPart(colorStr);

  const shadowValue: DtcgShadowValue = {
    offsetX,
    offsetY,
    blur,
    color,
  };

  return {
    $value: shadowValue,
    $type: "shadow",
    $extensions: {
      "com.ditto-app": {
        compositeType: "shadow",
        rawCss: parsed.value,
      },
    },
  };
}

// ── Border Builder ───────────────────────────

/**
 * Build a DTCG border token from a composite-border parsed value.
 *
 * Expected input: `"1px solid var(--border-subtle)"` or `"1px solid oklch(...)"`
 *
 * Tokenizes into width, style, and color. Color may be a var() reference
 * (resolved via referenceMap) or a direct oklch/hex value.
 */
function buildBorder(
  parsed: ParsedCompositeBorder,
  referenceMap: Map<string, string>,
): DtcgToken {
  const parts = parsed.value.trim().split(/\s+/);

  // A valid border has at least 3 parts: width, style, color.
  if (parts.length < 3) {
    return {
      $value: parsed.value,
      $type: "other",
      $extensions: {
        "com.ditto-app": {
          compositeType: "border",
          rawCss: `invalid border format: ${parsed.value}`,
        },
      },
    };
  }

  const width = parts[0] as string;
  const style = parts[1] as string;
  const colorStr = parts.slice(2).join(" ");
  const color = resolveColorPart(colorStr, referenceMap);

  const borderValue: DtcgBorderValue = {
    color,
    style,
    width,
  };

  return {
    $value: borderValue,
    $type: "border",
    $extensions: {
      "com.ditto-app": {
        compositeType: "border",
        rawCss: parsed.value,
      },
    },
  };
}

// ── Transition Builder ───────────────────────

/**
 * Build a DTCG transition token from a composite-transition parsed value.
 *
 * Expected input: `"var(--motion-duration-slow) var(--motion-easing-standard)"`
 *
 * First space-separated token → duration, second → timingFunction.
 * Both are resolved via referenceMap; unresolved references kept as raw var().
 */
function buildTransition(
  parsed: ParsedCompositeTransition,
  referenceMap: Map<string, string>,
): DtcgToken {
  const tokens = extractVarReferences(parsed.value);

  const [durationToken, timingFunctionToken] = tokens;
  if (durationToken === undefined || timingFunctionToken === undefined) {
    return {
      $value: parsed.value,
      $type: "other",
      $extensions: {
        "com.ditto-app": {
          compositeType: "transition",
          rawCss: `invalid transition format: ${parsed.value}`,
        },
      },
    };
  }

  const duration = resolveVarReference(durationToken, referenceMap);
  const timingFunction = resolveVarReference(timingFunctionToken, referenceMap);

  const transitionValue: DtcgTransitionValue = {
    duration,
    timingFunction,
  };

  return {
    $value: transitionValue,
    $type: "transition",
    $extensions: {
      "com.ditto-app": {
        compositeType: "transition",
        rawCss: parsed.value,
      },
    },
  };
}

// ── Shorthand Builder ────────────────────────

/**
 * Build a DTCG "other" token for shorthand values that cannot be
 * decomposed into a standard DTCG composite structure.
 *
 * Expected input: `"var(--space-10) var(--space-12)"`
 *
 * The raw value is preserved as-is, with an extension marking the
 * composite type as "shorthand".
 */
function buildShorthand(parsed: ParsedCompositeShorthand): DtcgToken {
  return {
    $value: parsed.value,
    $type: "other",
    $extensions: {
      "com.ditto-app": {
        compositeType: "shorthand",
        rawCss: parsed.value,
      },
    },
  };
}

// ── Helpers ──────────────────────────────────

/**
 * Parse a raw dimension string (e.g. "8px", "0") into the DTCG dimension structure.
 * Bare numbers default to px unit.
 */
function parseDimensionPart(
  raw: string,
  fallback: string,
): { value: string; type: "dimension"; unit: string } {
  const match = /^(-?[\d.]+)(px|rem|em|%)$/.exec(raw);
  if (match?.[1] !== undefined && match[2] !== undefined) {
    return { value: match[1], type: "dimension", unit: match[2] };
  }
  // Bare number (e.g. "0") — default to px.
  if (/^-?[\d.]+$/.test(raw)) {
    return { value: raw, type: "dimension", unit: "px" };
  }
  // Fallback for unparsable input.
  return { value: fallback, type: "dimension", unit: "px" };
}

/**
 * Convert a color string to hex.
 * Handles oklch() (with optional alpha), hex, and var() references.
 * For var() references, returns the raw var() string (caller should use resolveColorPart).
 */
function convertColorPart(colorStr: string): string {
  const trimmed = colorStr.trim();

  // Already a hex color.
  if (/^#[0-9a-fA-F]{3,8}$/.test(trimmed)) {
    return trimmed;
  }

  // oklch() color.
  if (isOklch(trimmed)) {
    const components = parseOklchString(trimmed);
    if (components) {
      return oklchToHex(
        components.l,
        components.c,
        components.h,
        components.alpha < 1 ? components.alpha : undefined,
      );
    }
  }

  // Fallback: return as-is (could be var(), named color, etc.).
  return trimmed;
}

/**
 * Resolve a color part that may be a var() reference or a direct color value.
 * If it's a var() reference and found in referenceMap, returns the DTCG path.
 * Otherwise converts to hex or returns the raw string.
 */
function resolveColorPart(
  colorStr: string,
  referenceMap: Map<string, string>,
): string {
  const trimmed = colorStr.trim();
  const varMatch = VAR_RE.exec(trimmed);

  if (varMatch) {
    const capturedName = varMatch[1];
    if (capturedName === undefined) return trimmed;
    const varName = capturedName.startsWith("--")
      ? capturedName.slice(2)
      : capturedName;
    const dtcgPath = referenceMap.get(varName);
    if (dtcgPath) {
      return dtcgPath;
    }
    // Unresolved — keep raw var() string.
    return trimmed;
  }

  // Direct color value — convert to hex.
  return convertColorPart(trimmed);
}

/**
 * Extract var() variable names from a space-separated composite string.
 * Returns an array of variable names (without `--` prefix).
 *
 * Example: `"var(--motion-duration-slow) var(--motion-easing-standard)"`
 *   → `["motion-duration-slow", "motion-easing-standard"]`
 */
function extractVarReferences(value: string): string[] {
  const results: string[] = [];
  const re = /var\(([^)]+)\)/g;
  let match: RegExpExecArray | null;
  while ((match = re.exec(value)) !== null) {
    const capturedName = match[1];
    if (capturedName === undefined) continue;
    const name = capturedName.startsWith("--") ? capturedName.slice(2) : capturedName;
    results.push(name);
  }
  return results;
}

/**
 * Resolve a single var() reference via referenceMap.
 * If the reference cannot be found, returns the raw `var(--name)` string.
 */
function resolveVarReference(
  varName: string,
  referenceMap: Map<string, string>,
): string {
  const dtcgPath = referenceMap.get(varName);
  if (dtcgPath) {
    return dtcgPath;
  }
  return `var(--${varName})`;
}
