// ─────────────────────────────────────────────
// Ditto DTCG Token Export — JSON Writer
// Converts resolved DTCG tokens into per-layer token files
// and per-theme override files.
// ─────────────────────────────────────────────

import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";

import type {
  DtcgToken,
  RawCssToken,
  TokenLayer,
} from "./types";
import { TOKEN_LAYERS } from "./types";
import { parseTokenValue } from "./reference-resolver";
import { parseOklchString, oklchToHex } from "./oklch-converter";

// ── Constants ────────────────────────────────

/** Theme file mapping: output filename → CSS selector pattern. */
const THEME_FILE_MAP = [
  { filename: "light.json", selectorPattern: "[data-theme=\"light\"]", excludePatterns: ["data-domain"] },
  { filename: "domain-signatures.json", selectorPattern: "data-domain", excludePatterns: ["data-theme=\"light\""] },
  { filename: "market-intl.json", selectorPattern: "data-market-region", excludePatterns: [] },
  { filename: "density-comfortable.json", selectorPattern: "data-density=\"comfortable\"", excludePatterns: [] },
  { filename: "density-dense.json", selectorPattern: "data-density=\"dense\"", excludePatterns: [] },
] as const;

// ── Path Utilities ───────────────────────────

/**
 * Convert a hyphenated token name to nested path segments.
 *
 * Strategy: split on hyphens, then greedily group segments that form
 * a known prefix (color group, component name, density, etc.) and
 * leave the rest as-is. Single-digit or numeric segments are treated
 * as leaf keys and never merged with the previous segment.
 *
 * Examples:
 *   "neutral-0"          → ["neutral", "0"]
 *   "brand-500"          → ["brand", "500"]
 *   "surface-panel-base" → ["surface", "panel-base"]
 *   "btn-sm-padding-y"   → ["btn", "sm", "padding-y"]
 *   "density-row-height" → ["density", "row-height"]
 *   "font-size-12"       → ["font", "size", "12"]
 *   "market-up-fg"       → ["market", "up-fg"]
 *   "brand-signature-fg" → ["brand", "signature-fg"]
 *   "risk-high-bg"       → ["risk", "high-bg"]
 *   "atmosphere-hue-shift" → ["atmosphere", "hue-shift"]
 */
export function tokenNameToNestedPath(name: string): string[] {
  const segments = name.split("-");

  if (segments.length <= 1) {
    return segments;
  }

  // Known sub-prefixes that should form their own nesting level
  // when they appear right after the namespace prefix.
  const SUB_PREFIXES: ReadonlySet<string> = new Set([
    // Font sub-types
    "size", "weight", "family", "line", "tracking", "leading",
    // Brand sub-types
    "signature", "accent",
    // Surface sub-types
    "panel", "strip", "overlay", "modal", "muted", "elevated", "app",
    // Text sub-types
    "primary", "secondary", "tertiary", "quaternary", "disabled", "inverse",
    "data", "stale", "label", "caption", "code", "link",
    // Border sub-types
    "subtle", "default", "strong",
    // Market sub-types
    "up", "down", "flat", "strong", "weak",
    // Risk sub-types
    "low", "medium", "high", "critical", "near", "breach",
    // Execution sub-types
    "pending", "partial", "filled", "cancelled", "rejected",
    // System sub-types
    "healthy", "degraded", "stale", "down", "recovering",
    // Data quality sub-types
    "fresh", "delayed", "missing", "partial", "revised",
    // Model sub-types
    "stable", "degrading", "drifting", "invalid", "candidate",
    // Agent sub-types
    "idle", "running", "waiting", "blocked", "failed",
    // Motion sub-types
    "duration", "easing",
    // Density sub-types
    "row", "cell", "panel", "section", "gutter", "strip", "toolbar",
    "header", "input", "action", "chart",
    // Shell sub-types
    "header", "rail", "sidebar", "main", "footer",
    // Component sub-types
    "sm", "md", "lg", "base",
    // Domain bg
    "bg",
    // Atmosphere sub-types
    "hue", "saturation", "chroma", "lightness", "shift",
  ]);

  const result: string[] = [];
  let i = 0;

  while (i < segments.length) {
    const seg = segments[i];
    if (seg === undefined) break;

    if (i === 0) {
      // First segment is always a namespace key
      result.push(seg);
      i++;
      continue;
    }

    // Pure numeric or hex-like segments are always leaf keys
    if (/^\d+$/.test(seg)) {
      result.push(seg);
      i++;
      continue;
    }

    // If the previous segment was numeric, this starts a new group
    const previousSegment = result.at(-1);
    if (previousSegment !== undefined && /^\d+$/.test(previousSegment)) {
      result.push(seg);
      i++;
      continue;
    }

    // Known sub-prefixes that should form their own nesting level
    if (SUB_PREFIXES.has(seg)) {
      result.push(seg);
      i++;
      continue;
    }

    // Otherwise, merge with the previous segment to form a compound key
    if (result.length > 0) {
      const previous = result.at(-1);
      if (previous === undefined) throw new Error(`Cannot group token path segment: ${name}`);
      result[result.length - 1] = `${previous}-${seg}`;
    } else {
      result.push(seg);
    }
    i++;
  }

  return result;
}

/**
 * Set a deeply nested value in an object, creating intermediate objects as needed.
 * If the path already has a non-object value at an intermediate position,
 * it will be overwritten with a plain object.
 */
export function setNestedValue(
  obj: Record<string, unknown>,
  path: string[],
  value: DtcgToken,
): void {
  if (path.length === 0) throw new Error("Cannot set a token at an empty path");
  let current: Record<string, unknown> = obj;

  for (let i = 0; i < path.length - 1; i++) {
    const key = path[i];
    if (key === undefined) throw new Error("Token path contains an empty segment");
    const next = current[key];

    if (next === undefined || next === null || typeof next !== "object" || Array.isArray(next)) {
      current[key] = {};
    }

    current = current[key] as Record<string, unknown>;
  }

  const leafKey = path.at(-1);
  if (leafKey === undefined) throw new Error("Cannot set a token at an empty path");
  current[leafKey] = value;
}

// ── Sorting Utility ──────────────────────────

/**
 * Recursively sort all keys in an object alphabetically.
 * Returns a new sorted object (does not mutate the input).
 */
function sortKeysDeep(value: unknown): unknown {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    return value;
  }

  const obj = value as Record<string, unknown>;
  const sorted: Record<string, unknown> = {};

  for (const key of Object.keys(obj).sort()) {
    sorted[key] = sortKeysDeep(obj[key]);
  }

  return sorted;
}

// ── JSON Serialization ───────────────────────

/**
 * Serialize a value to JSON with alphabetical key ordering and 2-space indentation.
 */
function serializeJson(value: unknown): string {
  return `${JSON.stringify(sortKeysDeep(value), null, 2)}\n`;
}

// ── Grouping Utility ─────────────────────────

/**
 * Group raw tokens by their CSS selector string.
 */
export function groupBySelector(tokens: RawCssToken[]): Map<string, RawCssToken[]> {
  const groups = new Map<string, RawCssToken[]>();

  for (const token of tokens) {
    const existing = groups.get(token.selector);
    if (existing) {
      existing.push(token);
    } else {
      groups.set(token.selector, [token]);
    }
  }

  return groups;
}

// ── Domain Extraction Utility ────────────────

/**
 * Extract domain name from a selector like `[data-domain="trading"]`
 * or `[data-theme="light"][data-domain="markets"]`.
 * Returns `undefined` if the selector does not target a specific domain.
 */
function extractDomainName(selector: string): string | undefined {
  const match = selector.match(/data-domain="([^"]+)"/);
  return match?.[1];
}

/**
 * Extract density preset name from a selector like `[data-density="comfortable"]`.
 * Returns `undefined` if the selector does not target a density preset.
 */
function extractDensityPreset(selector: string): string | undefined {
  const match = selector.match(/data-density="([^"]+)"/);
  return match?.[1];
}

// ── Token File Writer ────────────────────────

/**
 * Write 9 token files (one per layer) to `outputDir/tokens/`.
 * Each file contains `:root` default tokens nested by token name path.
 */
function writeTokenFiles(
  tokensDir: string,
  tokensByLayer: Map<TokenLayer, Map<string, DtcgToken>>,
): void {
  for (const layer of TOKEN_LAYERS) {
    const layerTokens = tokensByLayer.get(layer);
    if (!layerTokens || layerTokens.size === 0) {
      // Write empty object for layers with no tokens
      writeFileSync(join(tokensDir, `${layer}.json`), "{}\n");
      continue;
    }

    const nested: Record<string, unknown> = {};

    for (const [name, dtcgToken] of layerTokens) {
      const path = tokenNameToNestedPath(name);
      setNestedValue(nested, path, dtcgToken);
    }

    writeFileSync(join(tokensDir, `${layer}.json`), serializeJson(nested));
  }
}

// ── Theme File Writer ────────────────────────

/**
 * Build and write all theme override files to `outputDir/themes/`.
 *
 * This handles the five non-trivial theme files:
 *   - light.json
 *   - domain-signatures.json
 *   - market-intl.json
 *   - density-comfortable.json
 *   - density-dense.json
 *
 * Plus the empty dark.json (since `:root` defaults ARE dark).
 */
export function buildThemeFiles(
  tokens: RawCssToken[],
  defaultResolved: Map<string, DtcgToken>,
  outputDir: string,
): void {
  const themesDir = join(outputDir, "themes");

  // Filter to tokens with non-default context (not `:root`)
  const overrideTokens = tokens.filter((t) => t.selector !== ":root");

  // Group by selector
  const bySelector = groupBySelector(overrideTokens);

  // Build name-based lookup from the full DTCG path resolved map
  // Keys in defaultResolved are like "{base.brand.500}", we need "brand-500" lookup
  const nameToDtcg = new Map<string, DtcgToken>();
  for (const [dtcgPath, token] of defaultResolved) {
    const inner = dtcgPath.replace(/^\{|\}$/g, "");
    const dotIndex = inner.indexOf(".");
    if (dotIndex !== -1) {
      const layer = inner.slice(0, dotIndex);
      const name = inner.slice(dotIndex + 1);
      // Store with both the original name and layer-prefixed name
      nameToDtcg.set(name, token);
      nameToDtcg.set(`${layer}-${name.replace(/\./g, "-")}`, token);
    }
  }

  // Resolve theme override values from their raw CSS
  // Each override token has its own value that may differ from default
  const overrideDtcg = new Map<string, DtcgToken>();
  for (const token of overrideTokens) {
    const parsed = parseTokenValue(token.value);
    let dtcg: DtcgToken;

    if (parsed.type === "color") {
      // Resolve oklch to hex for theme overrides
      const components = parseOklchString(parsed.oklch);
      if (components) {
        const hex = oklchToHex(
          components.l, components.c, components.h,
          components.alpha < 1 ? components.alpha : undefined,
        );
        dtcg = { $value: hex, $type: "color", $extensions: { "com.ditto-app": { oklch: parsed.oklch } } };
      } else {
        dtcg = { $value: token.value, $type: "color" };
      }
    } else if (parsed.type === "relativeOklch") {
      // Relative oklch in theme overrides — keep raw for now
      dtcg = { $value: token.value, $type: "color" };
    } else if (parsed.type === "composite-shadow") {
      dtcg = { $value: token.value, $type: "composite" };
    } else if (parsed.type === "reference") {
      const refPath = nameToDtcg.get(parsed.variableName);
      dtcg = refPath ? { $value: refPath.$value, $type: refPath.$type }
        : { $value: token.value, $type: "other" };
    } else if (parsed.type === "composite-border") {
      dtcg = { $value: token.value, $type: "composite" };
    } else {
      dtcg = { $value: token.value, $type: "other" };
    }

    overrideDtcg.set(token.name, dtcg);
  }

  // Write empty dark.json — `:root` IS the dark default
  writeFileSync(join(themesDir, "dark.json"), "{}\n");

  // ── light.json ──────────────────────────────
  const lightObj: Record<string, unknown> = {};
  const lightSelectors = filterSelectors(bySelector, (sel) => {
    return sel === '[data-theme="light"]';
  });

  for (const token of lightSelectors) {
    const dtcg = overrideDtcg.get(token.name) ?? nameToDtcg.get(token.name);
    if (!dtcg) continue;

    const path = tokenNameToNestedPath(token.name);
    setNestedValue(lightObj, path, dtcg);
  }
  writeFileSync(join(themesDir, "light.json"), serializeJson(lightObj));

  // ── domain-signatures.json ──────────────────
  const domainObj: Record<string, unknown> = {};
  const domainSelectors = filterSelectors(bySelector, (sel) => {
    return sel.includes("data-domain") && !sel.includes("data-theme=\"light\"");
  });

  for (const token of domainSelectors) {
    const domain = extractDomainName(token.selector);
    if (!domain) continue;

    const dtcg = overrideDtcg.get(token.name) ?? nameToDtcg.get(token.name);
    if (!dtcg) continue;

    if (!domainObj[domain]) {
      domainObj[domain] = {};
    }

    const path = tokenNameToNestedPath(token.name);
    setNestedValue(domainObj[domain] as Record<string, unknown>, path, dtcg);
  }
  writeFileSync(join(themesDir, "domain-signatures.json"), serializeJson(domainObj));

  // ── light-domain overrides ──────────────────
  const lightDomainSelectors = filterSelectors(bySelector, (sel) => {
    return sel.includes("data-theme=\"light\"") && sel.includes("data-domain");
  });

  if (lightDomainSelectors.length > 0) {
    const lightDomainsObj: Record<string, unknown> = {};
    for (const token of lightDomainSelectors) {
      const domain = extractDomainName(token.selector);
      if (!domain) continue;

      const dtcg = overrideDtcg.get(token.name) ?? nameToDtcg.get(token.name);
      if (!dtcg) continue;

      if (!lightDomainsObj[domain]) {
        lightDomainsObj[domain] = {};
      }

      const path = tokenNameToNestedPath(token.name);
      setNestedValue(lightDomainsObj[domain] as Record<string, unknown>, path, dtcg);
    }

    if (Object.keys(lightDomainsObj).length > 0) {
      const domainFile = JSON.parse(
        readExistingFile(join(themesDir, "domain-signatures.json")),
      ) as Record<string, unknown>;
      domainFile["$light"] = lightDomainsObj;
      writeFileSync(
        join(themesDir, "domain-signatures.json"),
        serializeJson(domainFile),
      );
    }
  }

  // ── market-intl.json ────────────────────────
  const intlObj: Record<string, unknown> = {};
  const intlSelectors = filterSelectors(bySelector, (sel) => {
    return sel.includes("data-market-region");
  });

  for (const token of intlSelectors) {
    const dtcg = overrideDtcg.get(token.name) ?? nameToDtcg.get(token.name);
    if (!dtcg) continue;

    const path = tokenNameToNestedPath(token.name);
    setNestedValue(intlObj, path, dtcg);
  }
  writeFileSync(join(themesDir, "market-intl.json"), serializeJson(intlObj));

  // ── density-comfortable.json ────────────────
  writeDensityFile(themesDir, bySelector, overrideDtcg, nameToDtcg, "comfortable");

  // ── density-dense.json ──────────────────────
  writeDensityFile(themesDir, bySelector, overrideDtcg, nameToDtcg, "dense");
}

/**
 * Write a single density theme file for a given preset name.
 */
function writeDensityFile(
  themesDir: string,
  bySelector: Map<string, RawCssToken[]>,
  overrideDtcg: Map<string, DtcgToken>,
  nameToDtcg: Map<string, DtcgToken>,
  preset: string,
): void {
  const obj: Record<string, unknown> = {};
  const densitySelectors = filterSelectors(bySelector, (sel) => {
    return extractDensityPreset(sel) === preset;
  });

  for (const token of densitySelectors) {
    const dtcg = overrideDtcg.get(token.name) ?? nameToDtcg.get(token.name);
    if (!dtcg) continue;

    const path = tokenNameToNestedPath(token.name);
    setNestedValue(obj, path, dtcg);
  }

  writeFileSync(join(themesDir, `density-${preset}.json`), serializeJson(obj));
}

// ── Selector Filtering ───────────────────────

/**
 * Filter tokens from a selector-grouped map by a predicate on the selector string.
 * Returns a flat array of matching RawCssTokens.
 */
function filterSelectors(
  bySelector: Map<string, RawCssToken[]>,
  predicate: (selector: string) => boolean,
): RawCssToken[] {
  const result: RawCssToken[] = [];

  for (const [selector, tokens] of bySelector) {
    if (predicate(selector)) {
      result.push(...tokens);
    }
  }

  return result;
}

// ── File Read Helper ─────────────────────────

/**
 * Read an existing file synchronously. Used to re-read a file we just wrote
 * when we need to augment it (e.g. appending `$light` domain overrides).
 */
function readExistingFile(filePath: string): string {
  return readFileSync(filePath, "utf-8");
}

// ── Main Entry Point ─────────────────────────

/**
 * Write all DTCG JSON output files.
 *
 * Creates the directory structure and writes:
 *   - 9 token files (one per layer) in `outputDir/tokens/`
 *   - 6 theme files in `outputDir/themes/`
 *
 * @param outputDir - Base output directory (e.g. "dist/tokens")
 * @param tokensByLayer - Resolved DTCG tokens grouped by layer
 * @param themeOverrides - Additional theme override tokens (keyed by theme name)
 * @param allRawTokens - All raw CSS tokens (used by buildThemeFiles to extract overrides)
 */
export function writeDtcgFiles(
  outputDir: string,
  tokensByLayer: Map<TokenLayer, Map<string, DtcgToken>>,
  _themeOverrides: Map<string, Map<string, DtcgToken>>,
  allRawTokens?: RawCssToken[],
): void {
  const tokensDir = join(outputDir, "tokens");
  const themesDir = join(outputDir, "themes");

  // Ensure directory structure exists
  mkdirSync(tokensDir, { recursive: true });
  mkdirSync(themesDir, { recursive: true });

  // Write per-layer token files
  writeTokenFiles(tokensDir, tokensByLayer);

  // Build a resolved token lookup from all layers for theme file generation
  const resolvedTokens = new Map<string, DtcgToken>();
  for (const layerTokens of tokensByLayer.values()) {
    for (const [name, dtcg] of layerTokens) {
      resolvedTokens.set(name, dtcg);
    }
  }

  // Write theme override files
  if (allRawTokens) {
    buildThemeFiles(allRawTokens, resolvedTokens, outputDir);
  } else {
    // Write empty theme files if no raw tokens provided
    writeFileSync(join(themesDir, "dark.json"), "{}\n");
    for (const themeFile of THEME_FILE_MAP) {
      writeFileSync(join(themesDir, themeFile.filename), "{}\n");
    }
  }
}
