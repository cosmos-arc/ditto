// ─────────────────────────────────────────────
// Ditto DTCG Token Export — Reference Resolver
// Phase A: Build token-name → DTCG path mapping table.
// Phase B: Parse each token's raw CSS value, resolve references,
//          and produce DtcgToken objects for JSON output.
// ─────────────────────────────────────────────

import {
  parseOklchString,
  oklchToHex,
  resolveRelativeOklch,
  isOklch,
  isRelativeOklch,
} from "./oklch-converter";

import type {
  RawCssToken,
  ParsedValue,
  DtcgToken,
  DittoExtensionMeta,
  TokenLayer,
} from "./types";

// ── Regex Patterns ───────────────────────────

const RELATIVE_OKLCH_RE =
  /oklch\(\s*from\s+var\(([^)]+)\)\s+([\w%]+)\s+([\w]+)\s+([\w]+)(?:\s*\/\s*([\d.]+))?\s*\)/;

/** Single CSS variable reference with no fallback. Pattern: var(--name). */
const VAR_SIMPLE_RE = /^var\((--?[a-zA-Z0-9_-]+)\)$/;

/** CSS variable reference with a fallback value. Pattern: var(--name, fallback). */
const VAR_FALLBACK_RE = /^var\((--?[a-zA-Z0-9_-]+),\s*(.+)\)$/;

/** Dimension: number + rem|px|em|%. Matches values like `0.5rem`, `16px`, `1px`. */
const DIMENSION_RE = /^-?[\d.]+(rem|px|em|%)$/;

/** Number: integer or float (but NOT matching dimension or percentage patterns). */
const NUMBER_RE = /^-?[\d.]+$/;

/** Duration: number + ms|s. Matches `100ms`, `45s`. */
const DURATION_RE = /^-?[\d.]+(ms|s)$/;

/** Cubic bezier: `cubic-bezier(...)`. */
const CUBIC_BEZIER_RE = /^cubic-bezier\(/;

/** Composite shadow: `0 8px 24px oklch(...)` or `0px 8px 24px oklch(...)`. */
const COMPOSITE_SHADOW_RE =
  /^-?[\d.]+(?:px)?\s+-?[\d.]+(?:px)?\s+[\d.]+(?:px)?\s+oklch\(/;

/** Composite border shorthand: `1px solid var(...)` or `1px solid oklch(...)`. */
const COMPOSITE_BORDER_RE =
  /^-?[\d.]+px\s+solid\s+(var\(|oklch\(|transparent|inherit)/;

/** Runtime dynamic oklch with calc(): `oklch(calc(...) calc(...) calc(...))`. */
const RUNTIME_DYNAMIC_RE =
  /oklch\(\s*calc\([\d.]+\s*\+\s*var\([^)]+\)\)\s+calc\([\d.]+\s*\+\s*var\([^)]+\)\)\s+calc\([\d.]+\s*\+\s*var\([^)]+\)\)\s*\)/;

/** Multi-line var shorthand (after whitespace normalization): two or more var() with spaces. */
const MULTI_VAR_RE = /^(var\([^)]+\)\s+)+var\([^)]+\)$/;

/** Font family: contains comma-separated values with at least one quoted string. */
const FONT_FAMILY_RE = /'.+'/;

/** CSS string value: quoted or escaped. Matches `'\25B2'` or `'foo'`. */
const CSS_STRING_RE = /^'[^']*'$|^"[^"]*"$/;

/** Strip leading `--` from a CSS variable name. */
function stripVarPrefix(name: string): string {
  return name.startsWith("--") ? name.slice(2) : name;
}

// ── Layer Processing Order ───────────────────
// L1 base first (no cross-layer deps), then L2–L8 in dependency order.

const LAYER_ORDER: readonly TokenLayer[] = [
  "base",
  "semantic",
  "atmosphere",
  "shell",
  "data-viz",
  "component",
  "interaction",
  "domain",
  "density",
];

// ── Phase A: Reference Map Builder ───────────

/**
 * Build a mapping from token name (without CSS custom property prefix) to its DTCG path.
 *
 * Only includes tokens with context "default" (`:root` selector).
 * Theme overrides (light, domain, density, etc.) are excluded because
 * they override existing paths rather than creating new ones.
 *
 * @param tokens - All parsed CSS tokens (any context).
 * @returns Map where key = token name, value = DTCG reference like `{base.brand.500}`.
 */
export function buildReferenceMap(
  tokens: RawCssToken[],
): Map<string, string> {
  const map = new Map<string, string>();

  for (const token of tokens) {
    if (token.context !== "default") continue;

    const path = tokenToDtcgPath(token.name, token.layer);
    map.set(token.name, path);
  }

  return map;
}

// ── Phase B: Token Resolution ────────────────

/**
 * Resolve all tokens into DTCG format.
 *
 * Processes tokens in layer dependency order (base first) so that
 * var() references in L2–L8 can be resolved against already-processed L1 tokens.
 *
 * @param tokens - All parsed CSS tokens (any context).
 * @returns Map where key = DTCG path (e.g. `{base.brand.500}`), value = resolved DtcgToken.
 */
export function resolveAllTokens(
  tokens: RawCssToken[],
): Map<string, DtcgToken> {
  const result = new Map<string, DtcgToken>();

  // Group tokens by layer, preserving order of definition within each layer.
  // Only include :root (default context) tokens — theme overrides are handled
  // separately by the writer module.
  const byLayer = new Map<TokenLayer, RawCssToken[]>();
  for (const layer of LAYER_ORDER) {
    byLayer.set(layer, []);
  }
  for (const token of tokens) {
    if (token.context !== "default") continue;
    const arr = byLayer.get(token.layer);
    if (arr) {
      arr.push(token);
    }
  }

  // Build the global reference map (name → DTCG path) for all :root tokens.
  const refMap = buildReferenceMap(tokens);

  // Internal resolution state: name → resolved DtcgToken (populated layer by layer).
  const resolvedMap = new Map<string, DtcgToken>();

  for (const layer of LAYER_ORDER) {
    const layerTokens = byLayer.get(layer);
    if (!layerTokens) continue;

    for (const token of layerTokens) {
      const dtcgPath = tokenToDtcgPath(token.name, token.layer);

      const parsed = parseTokenValue(token.value);
      const resolved = resolveParsedValue(
        parsed,
        token,
        refMap,
        resolvedMap,
      );

      result.set(dtcgPath, resolved);
      resolvedMap.set(token.name, resolved);
    }
  }

  return result;
}

/**
 * Resolve theme override tokens into DTCG format.
 * Similar to resolveAllTokens but only processes non-default context tokens.
 */
export function resolveThemeOverrides(
  tokens: RawCssToken[],
  defaultResolved: Map<string, DtcgToken>,
): Map<string, Map<string, DtcgToken>> {
  const result = new Map<string, Map<string, DtcgToken>>();
  const refMap = buildReferenceMap(tokens);

  for (const token of tokens) {
    if (token.context === "default") continue;

    const dtcgPath = tokenToDtcgPath(token.name, token.layer);
    const parsed = parseTokenValue(token.value);
    const resolvedMap = new Map<string, DtcgToken>();
    for (const [path, dtcg] of defaultResolved) {
      // Extract name from path: {base.brand.500} → brand-500
      const inner = path.replace(/^\{(.+)\}$/, "$1");
      const name = inner.replace(/^[a-z-]+\./, "");
      resolvedMap.set(name, dtcg);
    }

    const resolved = resolveParsedValue(parsed, token, refMap, resolvedMap);

    const themeKey = token.selector;
    if (!result.has(themeKey)) {
      result.set(themeKey, new Map());
    }
    result.get(themeKey)!.set(dtcgPath, resolved);
  }

  return result;
}

// ── Value Parser ─────────────────────────────

/**
 * Parse a raw CSS value string into a `ParsedValue` discriminated union.
 *
 * This function does NOT resolve references — it only classifies the value pattern.
 * The classification order matters: more specific patterns are checked first.
 */
export function parseTokenValue(rawValue: string): ParsedValue {
  const trimmed = rawValue.trim();

  // 1. Transparent keyword
  if (trimmed === "transparent") {
    return { type: "transparent" };
  }

  // 2. CSS string value (quoted)
  if (CSS_STRING_RE.test(trimmed)) {
    return { type: "string", value: trimmed };
  }

  // 3. Runtime dynamic oklch (calc() + var() inside oklch())
  // Must check before standard oklch since it also contains oklch().
  if (RUNTIME_DYNAMIC_RE.test(trimmed)) {
    return { type: "runtimeDynamic", value: trimmed };
  }

  // 3b. Composite shadow (before standard oklch since shadow contains oklch())
  if (COMPOSITE_SHADOW_RE.test(trimmed)) {
    return { type: "composite-shadow", value: trimmed };
  }

  // 4. Relative oklch: oklch(from var(--xxx) l c h / alpha)
  if (isRelativeOklch(trimmed)) {
    const match = RELATIVE_OKLCH_RE.exec(trimmed);
    if (match?.[1] !== undefined) {
      return {
        type: "relativeOklch",
        baseVariable: stripVarPrefix(match[1]),
        oklch: trimmed,
      };
    }
  }

  // 5. Standard oklch color
  if (isOklch(trimmed)) {
    return { type: "color", oklch: trimmed };
  }

  // 6. var() with fallback
  const fallbackMatch = VAR_FALLBACK_RE.exec(trimmed);
  if (fallbackMatch?.[1] !== undefined && fallbackMatch[2] !== undefined) {
    return {
      type: "referenceWithFallback",
      variableName: stripVarPrefix(fallbackMatch[1].trim()),
      fallback: fallbackMatch[2].trim(),
    };
  }

  // 7. Simple var() reference
  const simpleMatch = VAR_SIMPLE_RE.exec(trimmed);
  if (simpleMatch?.[1] !== undefined) {
    return {
      type: "reference",
      variableName: stripVarPrefix(simpleMatch[1].trim()),
    };
  }

  // 8. Composite border shorthand (before dimension check, since `1px` alone is a dimension)
  if (COMPOSITE_BORDER_RE.test(trimmed)) {
    return { type: "composite-border", value: trimmed };
  }

  // 9. Cubic bezier
  if (CUBIC_BEZIER_RE.test(trimmed)) {
    return { type: "cubicBezier", value: trimmed };
  }

  // 11. Duration (before number check, since `200` alone is a number)
  if (DURATION_RE.test(trimmed)) {
    return { type: "duration", value: trimmed };
  }

  // 12. Dimension (rem, px, em, %)
  if (DIMENSION_RE.test(trimmed)) {
    return { type: "dimension", value: trimmed };
  }

  // 13. Number (pure numeric)
  if (NUMBER_RE.test(trimmed)) {
    const num = parseFloat(trimmed);
    // Heuristic: if the number is a typical font-weight range (1-1000),
    // classify as fontWeight; otherwise as number.
    // Font weights in the token system are 400, 500, 600 etc.
    // Other numbers like 0.85, 1.0, 7 are generic numbers.
    if (Number.isInteger(num) && num >= 1 && num <= 1000) {
      return { type: "fontWeight", value: num };
    }
    return { type: "number", value: num };
  }

  // 14. Multi-var shorthand (e.g. `var(--a) var(--b)` or `var(--a) var(--b) var(--c)`)
  if (MULTI_VAR_RE.test(trimmed)) {
    return { type: "composite-shorthand", value: trimmed };
  }

  // 15. Font family (contains quoted strings with commas)
  if (FONT_FAMILY_RE.test(trimmed) && trimmed.includes(",")) {
    return { type: "fontFamily", value: trimmed };
  }

  // 16. Catch-all unknown
  return { type: "unknown", value: trimmed };
}

// ── Parsed Value → DtcgToken Resolution ──────

/**
 * Resolve a parsed value into a fully-formed DtcgToken.
 *
 * Uses the reference map and already-resolved tokens to convert
 * var() references into DTCG paths, oklch into hex, etc.
 */
function resolveParsedValue(
  parsed: ParsedValue,
  token: RawCssToken,
  refMap: Map<string, string>,
  resolvedMap: Map<string, DtcgToken>,
): DtcgToken {
  const extension: DittoExtensionMeta = {
    source: token.sourceFile,
    layer: token.layer,
  };

  switch (parsed.type) {
    case "color": {
      const components = parseOklchString(parsed.oklch);
      if (!components) {
        return makeOtherToken(parsed.oklch, extension);
      }
      const hex = oklchToHex(
        components.l,
        components.c,
        components.h,
        components.alpha < 1 ? components.alpha : undefined,
      );
      extension.oklch = parsed.oklch;
      return { $value: hex, $type: "color", $extensions: { "com.ditto-app": extension } };
    }

    case "relativeOklch": {
      const baseToken = lookupReferencedToken(
        parsed.baseVariable,
        resolvedMap,
      );
      if (!baseToken) {
        // Cannot resolve base token — keep raw value, note the issue.
        extension.oklch = parsed.oklch;
        extension.rawCss = `unresolved base: ${parsed.baseVariable}`;
        return {
          $value: parsed.oklch,
          $type: "color",
          $extensions: { "com.ditto-app": extension },
        };
      }

      // Extract the alpha from the relative oklch expression.
      const relMatch = RELATIVE_OKLCH_RE.exec(parsed.oklch);
      if (!relMatch) {
        return makeOtherToken(parsed.oklch, extension);
      }
      const alpha = relMatch[5] !== undefined ? parseFloat(relMatch[5]) : 1;

      // Look up the base token's oklch from its extensions.
      const baseOklch = baseToken.$extensions?.["com.ditto-app"]?.oklch;
      if (!baseOklch) {
        // Base token has no oklch metadata — cannot resolve relative expression.
        extension.oklch = parsed.oklch;
        extension.rawCss = `base token ${parsed.baseVariable} has no oklch metadata`;
        return {
          $value: parsed.oklch,
          $type: "color",
          $extensions: { "com.ditto-app": extension },
        };
      }

      const resolved = resolveRelativeOklch(baseOklch, alpha);
      extension.oklch = resolved.oklch;
      return {
        $value: resolved.hex,
        $type: "color",
        $extensions: { "com.ditto-app": extension },
      };
    }

    case "reference": {
      const refPath = refMap.get(parsed.variableName);
      if (refPath) {
        // Inherit type from the resolved target if available.
        const resolved = resolvedMap.get(parsed.variableName);
        const type = resolved?.$type ?? "color";
        return { $value: refPath, $type: type };
      }
      // Unresolved reference — keep as var() string.
      return {
        $value: `var(--${parsed.variableName})`,
        $type: "color",
        $extensions: {
          "com.ditto-app": {
            ...extension,
            rawCss: `unresolved reference: --${parsed.variableName}`,
          },
        },
      };
    }

    case "referenceWithFallback": {
      // Attempt to resolve the primary reference.
      const primaryPath = refMap.get(parsed.variableName);
      if (primaryPath) {
        const resolved = resolvedMap.get(parsed.variableName);
        const type = resolved?.$type ?? "color";
        const fallbackExt: DittoExtensionMeta = {
          ...extension,
          rawCss: parsed.fallback,
        };
        return {
          $value: primaryPath,
          $type: type,
          $extensions: { "com.ditto-app": fallbackExt },
        };
      }
      // Primary unresolvable — try fallback.
      const fallbackParsed = parseTokenValue(parsed.fallback);
      const fallbackToken = resolveParsedValue(
        fallbackParsed,
        token,
        refMap,
        resolvedMap,
      );
      return {
        $value: fallbackToken.$value,
        $type: fallbackToken.$type,
        $extensions: {
          "com.ditto-app": {
            ...extension,
            rawCss: `fallback from ${parsed.variableName}`,
          },
        },
      };
    }

    case "runtimeDynamic": {
      // Runtime-dynamic tokens cannot be resolved statically.
      // Provide a sensible fallback hex based on the base (dark) value.
      const fallbackHex = extractFallbackFromDynamic(parsed.value);
      extension.dynamic = true;
      extension.rawCss = parsed.value;
      return {
        $value: fallbackHex,
        $type: "color",
        $extensions: { "com.ditto-app": extension },
      };
    }

    case "dimension":
      return { $value: parsed.value, $type: "dimension" };

    case "number":
      return { $value: String(parsed.value), $type: "number" };

    case "fontFamily":
      return { $value: parsed.value, $type: "fontFamily" };

    case "fontWeight":
      return { $value: String(parsed.value), $type: "fontWeight" };

    case "cubicBezier":
      return { $value: parsed.value, $type: "cubicBezier" };

    case "duration":
      return { $value: parsed.value, $type: "duration" };

    case "composite-shadow":
      return { $value: parsed.value, $type: "composite" };

    case "composite-border":
      return { $value: parsed.value, $type: "composite" };

    case "composite-transition":
      return { $value: parsed.value, $type: "composite" };

    case "composite-shorthand":
      return { $value: parsed.value, $type: "other" };

    case "transparent":
      return { $value: "transparent", $type: "color" };

    case "string":
      return { $value: parsed.value, $type: "other" };

    case "unknown":
      return makeOtherToken(parsed.value, extension);
  }
}

// ── Helpers ──────────────────────────────────

/**
 * Convert a token name and layer into a DTCG path string.
 *
 * Hyphens in the name become dots in the path:
 *   "brand-500" + "base" → "{base.brand.500}"
 *   "btn-sm-padding-y" + "component" → "{component.btn.sm.padding-y}"
 *
 * Strips layer prefix from name if present to avoid doubling:
 *   "interaction-focus-ring" + "interaction" → "{interaction.focus.ring}"
 */
function tokenToDtcgPath(name: string, layer: TokenLayer): string {
  const prefix = `${layer}-`;
  const strippedName = name.startsWith(prefix) ? name.slice(prefix.length) : name;
  const dottedName = strippedName.replace(/-/g, ".");
  return `{${layer}.${dottedName}}`;
}

/**
 * Look up a referenced token's resolved DtcgToken by variable name.
 * Handles both prefixed and unprefixed variable names.
 */
function lookupReferencedToken(
  variableName: string,
  resolvedMap: Map<string, DtcgToken>,
): DtcgToken | null {
  // Strip `--` prefix if present.
  const name = variableName.startsWith("--")
    ? variableName.slice(2)
    : variableName;
  return resolvedMap.get(name) ?? null;
}

/**
 * Create a fallback hex for runtime-dynamic tokens by extracting the
 * base numeric values from calc() expressions and computing a static oklch.
 *
 * Example input: `oklch(calc(0.166 + var(...)) calc(0.010 + var(...)) calc(253 + var(...)))`
 * Returns the hex for `oklch(0.166 0.010 253)` (ignoring the var() shifts).
 */
function extractFallbackFromDynamic(rawValue: string): string {
  // Extract the base numbers from calc(N + var(...)) patterns.
  const calcRe = /calc\(([\d.]+)\s*\+/g;
  const baseValues: number[] = [];
  let match: RegExpExecArray | null;
  while ((match = calcRe.exec(rawValue)) !== null) {
    const captured = match[1];
    if (captured !== undefined) baseValues.push(parseFloat(captured));
  }

  if (baseValues.length >= 3) {
    const [lightness, chroma, hue] = baseValues;
    if (lightness === undefined || chroma === undefined || hue === undefined) return "#28282e";
    try {
      return oklchToHex(lightness, chroma, hue);
    } catch {
      // Fall through to opaque hex.
    }
  }

  // Opaque fallback: return neutral-0's hex as a safe default.
  // This should rarely happen.
  return "#28282e";
}

/**
 * Create an "other" type token for values that don't fit known categories.
 */
function makeOtherToken(
  value: string,
  extension?: DittoExtensionMeta,
): DtcgToken {
  if (extension) {
    return {
      $value: value,
      $type: "other",
      $extensions: { "com.ditto-app": extension },
    };
  }
  return { $value: value, $type: "other" };
}
