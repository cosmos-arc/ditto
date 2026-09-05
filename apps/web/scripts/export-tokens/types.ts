// ─────────────────────────────────────────────
// Ditto DTCG Token Export — Shared Type Definitions
// All modules in the export pipeline import from this file.
// ─────────────────────────────────────────────

// ── Token Layer Enum ──────────────────────────
// Maps 1:1 to the 9 CSS token source files:
//   tokens-{layer}.css in src/styles/design-tokens/

export const TOKEN_LAYERS = [
  "base",
  "semantic",
  "atmosphere",
  "shell",
  "data-viz",
  "component",
  "interaction",
  "domain",
  "density",
] as const;

export type TokenLayer = (typeof TOKEN_LAYERS)[number];

/** Derive TokenLayer from source filename (e.g. "tokens-base.css" -> "base"). */
export function layerFromFilename(filename: string): TokenLayer {
  const match = filename.match(/^tokens-(.+)\.css$/);
  if (!match) {
    throw new Error(`Cannot derive layer from filename: ${filename}`);
  }
  const candidate = match[1];
  if (TOKEN_LAYERS.includes(candidate as TokenLayer)) {
    return candidate as TokenLayer;
  }
  throw new Error(`Unknown token layer: ${candidate}`);
}

// ── Theme Context ─────────────────────────────
// CSS selectors that define token overrides per context.

export const THEME_CONTEXTS = [
  "default",
  "light",
  "domain",
  "density",
  "intl",
  "lightDomain",
] as const;

export type ThemeContext = (typeof THEME_CONTEXTS)[number];

/** Classify a CSS selector into a ThemeContext. */
export function themeContextFromSelector(selector: string): ThemeContext {
  if (selector === ":root") return "default";
  if (selector.includes("light")) return selector.includes("domain") ? "lightDomain" : "light";
  if (selector.includes("domain")) return "domain";
  if (selector.includes("density")) return "density";
  if (selector.includes("intl") || selector.includes("market-intl")) return "intl";
  return "default";
}

// ── Raw CSS Token ─────────────────────────────
// Parsed directly from CSS files before value classification.

export interface RawCssToken {
  /** Token name without `--` prefix. e.g. "brand-500" */
  name: string;
  /** Raw CSS value string as it appears in the stylesheet. */
  value: string;
  /** Source filename. e.g. "tokens-base.css" */
  sourceFile: string;
  /** CSS selector where this token was defined. e.g. ":root" or "[data-theme='light']" */
  selector: string;
  /** Token layer derived from sourceFile. */
  layer: TokenLayer;
  /** Theme context derived from selector. */
  context: ThemeContext;
}

// ── Parsed Value Discriminated Union ──────────
// Covers every value pattern found in the 9 CSS token source files.

/** `oklch(0.640 0.120 235)` or `oklch(0.640 0.120 235 / 0.50)` */
export interface ParsedColor {
  type: "color";
  oklch: string;
}

/** `0.5rem`, `1px`, `16px`, `2.25rem` */
export interface ParsedDimension {
  type: "dimension";
  value: string;
}

/** `1.0`, `0.85`, `0.5`, `400` */
export interface ParsedNumber {
  type: "number";
  value: number;
}

/** `'Inter', system-ui, sans-serif` — comma-separated font family list. */
export interface ParsedFontFamily {
  type: "fontFamily";
  value: string;
}

/** `400`, `500`, `600` — numeric font weight. */
export interface ParsedFontWeight {
  type: "fontWeight";
  value: number;
}

/** `cubic-bezier(0.4, 0, 0.2, 1)` */
export interface ParsedCubicBezier {
  type: "cubicBezier";
  value: string;
}

/** `100ms`, `200ms`, `45s` */
export interface ParsedDuration {
  type: "duration";
  value: string;
}

/** `var(--brand-500)` — single variable reference, no fallback. */
export interface ParsedReference {
  type: "reference";
  variableName: string;
}

/** `var(--surface-app-atmosphere, var(--neutral-0))` — reference with fallback. */
export interface ParsedReferenceWithFallback {
  type: "referenceWithFallback";
  variableName: string;
  fallback: string;
}

/** `oklch(from var(--brand-500) l c h / 0.10)` — relative color syntax. */
export interface ParsedRelativeOklch {
  type: "relativeOklch";
  baseVariable: string;
  oklch: string;
}

/** `0 8px 24px oklch(0 0 0 / 0.4)` — composite box-shadow value. */
export interface ParsedCompositeShadow {
  type: "composite-shadow";
  value: string;
}

/** `1px solid var(--border-subtle)` — composite border shorthand. */
export interface ParsedCompositeBorder {
  type: "composite-border";
  value: string;
}

/** `var(--motion-duration-slow) var(--motion-easing-standard)` — composite transition value. */
export interface ParsedCompositeTransition {
  type: "composite-transition";
  value: string;
}

/** `var(--space-10) var(--space-12)` — composite shorthand with multiple var() references. */
export interface ParsedCompositeShorthand {
  type: "composite-shorthand";
  value: string;
}

/** `oklch(calc(0.166 + var(...)) calc(0.010 + var(...)) calc(253 + var(...)))` — runtime-dynamic atmosphere tokens. */
export interface ParsedRuntimeDynamic {
  type: "runtimeDynamic";
  value: string;
}

/** `transparent` */
export interface ParsedTransparent {
  type: "transparent";
}

/** `'\25B2'` — CSS string values (unicode escapes, content property values). */
export interface ParsedString {
  type: "string";
  value: string;
}

/** Catch-all for values that don't match any known pattern. */
export interface ParsedUnknown {
  type: "unknown";
  value: string;
}

export type ParsedValue =
  | ParsedColor
  | ParsedDimension
  | ParsedNumber
  | ParsedFontFamily
  | ParsedFontWeight
  | ParsedCubicBezier
  | ParsedDuration
  | ParsedReference
  | ParsedReferenceWithFallback
  | ParsedRelativeOklch
  | ParsedCompositeShadow
  | ParsedCompositeBorder
  | ParsedCompositeTransition
  | ParsedCompositeShorthand
  | ParsedRuntimeDynamic
  | ParsedTransparent
  | ParsedString
  | ParsedUnknown;

// ── Ditto Extension ───────────────────────────
// Custom DTCG extension namespace for Ditto-specific metadata.

export interface DittoExtensionMeta {
  /** Original oklch() value string (DTCG only supports hex). */
  oklch?: string;
  /** Source CSS file where this token was defined. */
  source?: string;
  /** Which layer this token belongs to. */
  layer?: TokenLayer;
  /** Whether this token is set by JS at runtime (e.g. --atmosphere-hue-shift). */
  dynamic?: boolean;
  /** Whether this token uses runtime-dynamic calc() expressions (e.g. --surface-app-atmosphere). */
  runtimeDynamic?: boolean;
  /** Original CSS value for runtime-dynamic tokens that cannot be resolved statically. */
  rawCss?: string;
  /** For shorthand composite tokens: the composite type classification. */
  compositeType?: "shadow" | "border" | "transition" | "shorthand";
}

// ── DTCG Output Token ─────────────────────────
// W3C Design Tokens Community Group format.

/**
 * Structured composite value shapes for DTCG shadow/border/transition tokens.
 * Plain strings are used for all other token types.
 */
export type DtcgCompositeValue =
  | DtcgShadowValue
  | DtcgBorderValue
  | DtcgTransitionValue;

export interface DtcgShadowValue {
  offsetX: { value: string; type: "dimension"; unit: string };
  offsetY: { value: string; type: "dimension"; unit: string };
  blur: { value: string; type: "dimension"; unit: string };
  color: string;
}

export interface DtcgBorderValue {
  color: string;
  style: string;
  width: string;
}

export interface DtcgTransitionValue {
  duration: string;
  timingFunction: string;
}

export interface DtcgToken {
  /** The resolved value — string for simple types, structured object for composites. */
  $value: string | DtcgCompositeValue;
  /** DTCG type classifier. */
  $type: DtcgType;
  /** Human-readable description of the token's purpose. */
  $description?: string;
  /** DTCG extensions for vendor-specific metadata. */
  $extensions?: {
    "com.ditto-app"?: DittoExtensionMeta;
  };
}

/** DTCG token type classifier (W3C spec). */
export const DTCG_TYPES = [
  "color",
  "dimension",
  "number",
  "fontFamily",
  "fontWeight",
  "cubicBezier",
  "duration",
  "shadow",
  "border",
  "transition",
  "composite",
  "other",
] as const;

export type DtcgType = (typeof DTCG_TYPES)[number];

// ── Pipeline Config ───────────────────────────

export interface ExportConfig {
  /** Root directory of the project. */
  projectRoot: string;
  /** Directory containing tokens-*.css files. */
  tokensDir: string;
  /** Output directory for generated JSON files. */
  outputDir: string;
  /** Whether to include tokens from non-default selectors (light, domain, etc.). */
  includeThemeOverrides: boolean;
}

/** A fully processed token ready for DTCG JSON output, grouped by layer. */
export interface LayerTokens {
  layer: TokenLayer;
  tokens: Record<string, DtcgToken>;
}
