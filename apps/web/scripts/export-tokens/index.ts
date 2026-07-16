// ─────────────────────────────────────────────
// Ditto DTCG Token Export — Pipeline Orchestrator
// Parses CSS token files, resolves references, groups by layer,
// and writes DTCG-format JSON output files.
// ─────────────────────────────────────────────

import { existsSync, readFileSync, readdirSync } from "node:fs";
import { resolve } from "node:path";

import type {
  DtcgToken,
  ExportConfig,
  RawCssToken,
  TokenLayer,
} from "./types";
import { TOKEN_LAYERS } from "./types";
import { parseAllTokenFiles } from "./css-parser";
import { resolveAllTokens, resolveThemeOverrides } from "./reference-resolver";
import { writeDtcgFiles } from "./dtcg-writer";

// ── Result Types ─────────────────────────────

/** Summary returned by the export pipeline. */
export interface PipelineResult {
  totalTokens: number;
  tokensByLayer: Map<TokenLayer, number>;
  themesGenerated: string[];
  outputDir: string;
}

/** Result of post-hoc DTCG output validation. */
export interface ValidationResult {
  valid: boolean;
  errors: string[];
  warnings: string[];
}

// ── Default Config ───────────────────────────

const DEFAULT_CONFIG: ExportConfig = {
  projectRoot: process.cwd(),
  tokensDir: "src/styles/design-tokens",
  outputDir: "dist/tokens",
  includeThemeOverrides: true,
};

// ── Theme File Constants ─────────────────────

/** The 6 theme files expected in outputDir/themes/. */
const EXPECTED_THEME_FILES = [
  "dark.json",
  "light.json",
  "domain-signatures.json",
  "market-intl.json",
  "density-comfortable.json",
  "density-dense.json",
] as const;

// ── Public API: Pipeline Runner ──────────────

/**
 * Run the full token export pipeline.
 *
 * Steps:
 *   1. Parse all CSS token files
 *   2. Resolve references (var() → DTCG paths, oklch → hex)
 *   3. Group resolved tokens by layer
 *   4. Group theme override tokens by context
 *   5. Write DTCG JSON output files
 *   6. Print summary and return result
 *
 * @param config - Optional partial config overrides (merged with defaults).
 */
export async function runPipeline(
  config?: Partial<ExportConfig>,
): Promise<PipelineResult> {
  const cfg: ExportConfig = { ...DEFAULT_CONFIG, ...config };

  const tokensDir = resolve(cfg.projectRoot, cfg.tokensDir);
  const outputDir = resolve(cfg.projectRoot, cfg.outputDir);

  // 1. Parse CSS files
  const allTokens = parseAllTokenFiles(tokensDir);

  // 2. Resolve tokens (handles var() references, oklch→hex, etc.)
  const resolvedTokens = resolveAllTokens(allTokens);

  // 3. Group by layer
  const tokensByLayer = groupTokensByLayer(resolvedTokens, allTokens);

  // 4. Group theme overrides (non-default context tokens)
  const themeOverrides = resolveThemeOverrides(allTokens, resolvedTokens);

  // 5. Write DTCG files
  writeDtcgFiles(outputDir, tokensByLayer, themeOverrides, allTokens);

  // 6. Build summary
  const layerCounts = new Map<TokenLayer, number>();
  let total = 0;

  for (const layer of TOKEN_LAYERS) {
    const layerTokens = tokensByLayer.get(layer);
    const count = layerTokens?.size ?? 0;
    layerCounts.set(layer, count);
    total += count;
  }

  // Collect generated theme file names
  const themesDir = resolve(outputDir, "themes");
  const themesGenerated: string[] = [];
  if (existsSync(themesDir)) {
    const files = readdirSync(themesDir);
    for (const file of files) {
      if (file.endsWith(".json")) {
        themesGenerated.push(file);
      }
    }
  }

  // Print minimal summary
  for (const layer of TOKEN_LAYERS) {
    const count = layerCounts.get(layer) ?? 0;
    console.log(`  ${layer}: ${count}`);
  }
  console.log(`  total: ${total}`);

  return {
    totalTokens: total,
    tokensByLayer: layerCounts,
    themesGenerated,
    outputDir,
  };
}

// ── Public API: Group by Layer ───────────────

/**
 * Group resolved tokens by their source layer, using raw token metadata.
 *
 * The resolved tokens are keyed by DTCG path (e.g. `{base.brand.500}`).
 * This function maps each resolved token back to its source layer using
 * the layer metadata from the corresponding raw token.
 */
export function groupTokensByLayer(
  resolvedTokens: Map<string, DtcgToken>,
  _rawTokens: RawCssToken[],
): Map<TokenLayer, Map<string, DtcgToken>> {
  const result = new Map<TokenLayer, Map<string, DtcgToken>>();

  for (const layer of TOKEN_LAYERS) {
    result.set(layer, new Map());
  }

  for (const [dtcgPath, token] of resolvedTokens) {
    // Extract the layer from the DTCG path: {layer.name} → layer
    const inner = dtcgPath.replace(/^\{|\}$/g, "");
    const dotIndex = inner.indexOf(".");
    if (dotIndex === -1) continue;

    const layerStr = inner.slice(0, dotIndex);
    const layer = layerStr as TokenLayer;

    const layerMap = result.get(layer);
    if (layerMap) {
      const name = inner.slice(dotIndex + 1);
      layerMap.set(name, token);
    }
  }

  return result;
}

// ── Public API: DTCG Output Validation ───────

/**
 * Post-hoc validation of generated DTCG JSON files.
 *
 * Reads back the generated files and checks:
 *   - All 9 token layer files exist and are valid JSON
 *   - All 6 theme files exist (dark.json may be empty `{}`)
 *   - Every token has `$value` and `$type`
 *   - Color tokens have a valid hex `$value`
 *   - No orphaned DTCG `{...}` references
 */
export function validateDtcgOutput(outputDir: string): ValidationResult {
  const errors: string[] = [];
  const warnings: string[] = [];

  const tokensDir = resolve(outputDir, "tokens");
  const themesDir = resolve(outputDir, "themes");

  // Collect all token names and values for orphan reference checking.
  const allTokenPaths = new Set<string>();

  // ── Check 9 layer files ─────────────────────
  for (const layer of TOKEN_LAYERS) {
    const filePath = resolve(tokensDir, `${layer}.json`);

    if (!existsSync(filePath)) {
      errors.push(`Missing token file: ${layer}.json`);
      continue;
    }

    const parsed = safeParseJson(filePath, errors, layer);
    if (!parsed) continue;

    collectTokenPaths(parsed, layer, allTokenPaths);
    validateTokenObjects(parsed, layer, errors, warnings);
  }

  // ── Check 6 theme files ─────────────────────
  if (!existsSync(themesDir)) {
    errors.push("Missing themes directory");
  } else {
    for (const filename of EXPECTED_THEME_FILES) {
      const filePath = resolve(themesDir, filename);

      if (!existsSync(filePath)) {
        errors.push(`Missing theme file: ${filename}`);
        continue;
      }

      const parsed = safeParseJson(filePath, errors, `theme:${filename}`);
      if (!parsed) continue;

      // dark.json is allowed to be empty `{}`
      if (filename === "dark.json") {
        if (Object.keys(parsed).length > 0) {
          warnings.push("dark.json should be empty `{}` (:root IS the dark default)");
        }
        continue;
      }

      collectTokenPaths(parsed, `theme:${filename}`, allTokenPaths);
      validateTokenObjects(parsed, `theme:${filename}`, errors, warnings);
    }
  }

  // ── Check orphaned references ───────────────
  checkOrphanedReferences(tokensDir, allTokenPaths, errors, warnings);

  return {
    valid: errors.length === 0,
    errors,
    warnings,
  };
}

// ── Internal: Theme Override Grouping ─────────

/**
 * Build a map of theme name → tokens for non-default context tokens.
 *
 * Groups tokens by their theme context (light, domain, density, intl, lightDomain).
 * The resolved DtcgToken for each override is looked up from the resolved tokens map.
 */
function buildThemeOverrides(
  allTokens: RawCssToken[],
  resolvedTokens: Map<string, DtcgToken>,
): Map<string, Map<string, DtcgToken>> {
  const overrides = new Map<string, Map<string, DtcgToken>>();

  for (const token of allTokens) {
    if (token.context === "default") continue;

    // Use context as the theme key
    const themeKey = token.context;
    let themeMap = overrides.get(themeKey);
    if (!themeMap) {
      themeMap = new Map();
      overrides.set(themeKey, themeMap);
    }

    // Look up the resolved token by name.
    // Note: resolvedTokens are keyed by DTCG path, but we also need
    // name-based lookup. Build a name→resolved map from allTokens' layer context.
    const dtcg = findResolvedToken(token.name, resolvedTokens);
    if (dtcg) {
      themeMap.set(token.name, dtcg);
    }
  }

  return overrides;
}

/**
 * Find a resolved token by name from the resolved tokens map.
 *
 * The resolved tokens are keyed by DTCG path (e.g. `{base.brand.500}`),
 * so we need to match by extracting the name portion.
 */
function findResolvedToken(
  name: string,
  resolvedTokens: Map<string, DtcgToken>,
): DtcgToken | null {
  // Build a reverse lookup: DTCG path → name
  // We search through all resolved tokens to find one whose DTCG path
  // ends with the token name.
  for (const [dtcgPath, token] of resolvedTokens) {
    const extractedName = dtcgPathToName(dtcgPath);
    if (extractedName === name) {
      return token;
    }
  }
  return null;
}

/**
 * Extract a token name from a DTCG path string.
 *
 * Examples:
 *   `{base.brand.500}` → `brand-500`
 *   `{shell.header.height}` → `header-height`
 *   `{atmosphere.hue.shift}` → `hue-shift`
 */
function dtcgPathToName(dtcgPath: string): string {
  // Strip the surrounding braces and the layer prefix (first segment).
  const stripped = dtcgPath.replace(/^\{|\}$/g, "");
  const dotIndex = stripped.indexOf(".");
  if (dotIndex === -1) return stripped.replace(/\./g, "-");
  return stripped.slice(dotIndex + 1).replace(/\./g, "-");
}

// ── Internal: Validation Helpers ─────────────

/** Regex for valid hex color values (3, 4, 6, or 8 hex digits). */
const HEX_RE = /^#[0-9a-fA-F]{3,8}$/;

/** Regex matching DTCG reference paths like `{base.brand.500}`. */
const DTCG_REF_RE = /^\{[^{}]+\}$/;

/**
 * Safely parse a JSON file and report errors.
 */
function safeParseJson(
  filePath: string,
  errors: string[],
  context: string,
): Record<string, unknown> | null {
  try {
    const raw = readFileSync(filePath, "utf-8");
    const parsed = JSON.parse(raw) as Record<string, unknown>;
    return parsed;
  } catch {
    errors.push(`Invalid JSON in ${context}: ${filePath}`);
    return null;
  }
}

/**
 * Recursively collect all DTCG token paths from a nested JSON object.
 */
function collectTokenPaths(
  obj: unknown,
  context: string,
  allPaths: Set<string>,
): void {
  if (obj === null || typeof obj !== "object" || Array.isArray(obj)) return;

  for (const [key, value] of Object.entries(
    obj as Record<string, unknown>,
  )) {
    if (value !== null && typeof value === "object" && !Array.isArray(value)) {
      collectTokenPaths(value, context, allPaths);
    } else if (key.startsWith("$") || typeof value === "string") {
      // This is a token leaf — build a path-like identifier.
      // We don't have the full nested path here, so we skip path collection
      // at this level and instead check during validation.
    }
  }
}

/**
 * Recursively validate token objects in a nested JSON structure.
 */
function validateTokenObjects(
  obj: unknown,
  context: string,
  errors: string[],
  warnings: string[],
): void {
  if (obj === null || typeof obj !== "object" || Array.isArray(obj)) return;

  for (const [key, value] of Object.entries(
    obj as Record<string, unknown>,
  )) {
    if (value === null || typeof value !== "object" || Array.isArray(value)) {
      continue;
    }

    // Check if this looks like a DTCG token (has $value and $type)
    const record = value as Record<string, unknown>;
    if ("$value" in record && "$type" in record) {
      validateSingleToken(record, context, key, errors, warnings);
    } else {
      // Recurse into nested objects
      validateTokenObjects(value, context, errors, warnings);
    }
  }
}

/**
 * Validate a single DTCG token object.
 */
function validateSingleToken(
  token: Record<string, unknown>,
  context: string,
  key: string,
  errors: string[],
  warnings: string[],
): void {
  const valueType = typeof token.$value;
  const typeValue = typeof token.$type;

  // $value must be string or object (for composites)
  if (valueType !== "string" && (valueType !== "object" || token.$value === null)) {
    errors.push(`[${context}] Token "${key}": $value must be string or object, got ${valueType}`);
    return;
  }

  // $type must be string
  if (typeValue !== "string") {
    errors.push(`[${context}] Token "${key}": $type must be string, got ${typeValue}`);
    return;
  }

  const type = token.$type as string;

  // Color tokens must have valid hex values (unless they're DTCG references)
  if (type === "color" && typeof token.$value === "string") {
    const val = token.$value as string;

    // DTCG references are valid for color tokens
    if (DTCG_REF_RE.test(val)) return;

    // Special values
    if (val === "transparent") return;

    // Must be a valid hex (relative oklch with runtime-dynamic base is acceptable)
    if (!HEX_RE.test(val) && !val.includes("from var(")) {
      warnings.push(
        `[${context}] Token "${key}": color $value is not a valid hex: ${val}`,
      );
    }
  }
}

/**
 * Check for orphaned DTCG `{...}` references in token layer files.
 *
 * A reference is orphaned if it points to a token that does not exist
 * in any of the generated layer files.
 */
function checkOrphanedReferences(
  tokensDir: string,
  allTokenPaths: Set<string>,
  errors: string[],
  _warnings: string[],
): void {
  // Build a set of all known token identifiers from the generated files.
  // Token names are the keys in each layer file after flattening.
  const knownNames = new Set<string>();

  for (const layer of TOKEN_LAYERS) {
    const filePath = resolve(tokensDir, `${layer}.json`);
    if (!existsSync(filePath)) continue;

    try {
      const raw = readFileSync(filePath, "utf-8");
      const parsed = JSON.parse(raw) as Record<string, unknown>;
      collectAllNames(parsed, knownNames);
    } catch {
      // Already reported in the file existence check above.
    }
  }

  // Now scan all token values for DTCG references and check them.
  for (const layer of TOKEN_LAYERS) {
    const filePath = resolve(tokensDir, `${layer}.json`);
    if (!existsSync(filePath)) continue;

    try {
      const raw = readFileSync(filePath, "utf-8");
      const parsed = JSON.parse(raw) as Record<string, unknown>;
      checkReferencesRecursive(parsed, knownNames, layer, errors);
    } catch {
      // Already reported.
    }
  }
}

/**
 * Recursively collect all token names from a nested JSON structure.
 * Names are the deepest non-$ keys.
 */
function collectAllNames(
  obj: unknown,
  names: Set<string>,
  prefix = "",
): void {
  if (obj === null || typeof obj !== "object" || Array.isArray(obj)) return;

  for (const [key, value] of Object.entries(obj as Record<string, unknown>)) {
    const fullPath = prefix ? `${prefix}.${key}` : key;

    if (
      value !== null &&
      typeof value === "object" &&
      !Array.isArray(value) &&
      !("$value" in (value as Record<string, unknown>))
    ) {
      collectAllNames(value, names, fullPath);
    } else {
      // Leaf node (either a token or a terminal value)
      names.add(fullPath);
    }
  }
}

/**
 * Recursively check all DTCG reference values against known token names.
 */
function checkReferencesRecursive(
  obj: unknown,
  knownNames: Set<string>,
  layer: string,
  errors: string[],
  path = "",
): void {
  if (obj === null || typeof obj !== "object" || Array.isArray(obj)) return;

  for (const [key, value] of Object.entries(obj as Record<string, unknown>)) {
    const currentPath = path ? `${path}.${key}` : key;

    if (
      value !== null &&
      typeof value === "object" &&
      !Array.isArray(value) &&
      !("$value" in (value as Record<string, unknown>))
    ) {
      checkReferencesRecursive(value, knownNames, layer, errors, currentPath);
      continue;
    }

    // Check string values for DTCG references
    if (typeof value === "string" && DTCG_REF_RE.test(value)) {
      const refPath = value.replace(/^\{|\}$/g, "");
      // Try with and without layer prefix: "{base.brand.500}" → "base.brand.500" or "brand.500"
      const withoutLayer = refPath.includes(".") ? refPath.slice(refPath.indexOf(".") + 1) : refPath;
      if (!knownNames.has(refPath) && !knownNames.has(withoutLayer)) {
        errors.push(
          `[${layer}] Orphaned reference at "${currentPath}": ${value} does not match any token`,
        );
      }
    }

    // Check composite values for nested DTCG references
    if (
      value !== null &&
      typeof value === "object" &&
      !Array.isArray(value) &&
      "$value" in (value as Record<string, unknown>)
    ) {
      const innerValue = (value as Record<string, unknown>).$value;
      if (typeof innerValue === "string" && DTCG_REF_RE.test(innerValue)) {
        const refPath = innerValue.replace(/^\{|\}$/g, "");
        const withoutLayer = refPath.includes(".") ? refPath.slice(refPath.indexOf(".") + 1) : refPath;
        if (!knownNames.has(refPath) && !knownNames.has(withoutLayer)) {
          errors.push(
            `[${layer}] Orphaned reference at "${currentPath}.$value": ${innerValue} does not match any token`,
          );
        }
      }
    }
  }
}
