// ─────────────────────────────────────────────
// Ditto DTCG Token Export — CSS Token Parser
// Reads 9 tokens-*.css files and extracts all --name: value declarations,
// classifying each by layer (filename) and context (selector).
// ─────────────────────────────────────────────

import { readdirSync, readFileSync } from "node:fs";
import { basename } from "node:path";

import type { RawCssToken } from "./types";
import { layerFromFilename, themeContextFromSelector } from "./types";

// ── Constants ────────────────────────────────

/** Glob pattern for token source files (must match `tokens-{layer}.css`). */
const TOKEN_FILE_PREFIX = "tokens-";
const TOKEN_FILE_SUFFIX = ".css";

// ── Regex Patterns ───────────────────────────

/**
 * Matches a CSS selector block.
 * Captures:
 *   [1] = selector (e.g. `:root`, `[data-theme="light"]`)
 *   [2] = block content between `{` and `}` (may span multiple lines)
 *
 * Uses a lazy quantifier `[\s\S]*?` to match the first closing `}`,
 * which handles nested `var(...)` parentheses correctly because CSS
 * custom property blocks never contain nested `{}`.
 */
const SELECTOR_BLOCK_RE = /([^{}@][^{}]*?)\s*\{([\s\S]*?)\}/g;

/**
 * Matches a CSS custom property declaration inside a selector block.
 * Captures:
 *   [1] = property name with `--` prefix (e.g. `--brand-500`)
 *   [2] = raw value (everything between `:` and `;`, spanning multiple lines)
 *
 * The `[\s\S]*?` handles multi-line values like the atmosphere calc() tokens.
 */
const DECLARATION_RE = /(--[\w-]+)\s*:\s*([\s\S]*?);/g;

/**
 * Matches CSS block comments `/* ... *\/` for removal.
 * Uses `[\s\S]` to match across newlines.
 */
const COMMENT_RE = /\/\*[\s\S]*?\*\//g;

// ── Public API ───────────────────────────────

/**
 * Parse all 9 token CSS files in `tokensDir` and return a flat array of tokens.
 *
 * Reads every file matching `tokens-*.css`, extracts all `--name: value`
 * declarations from every selector block, and classifies each token by
 * its source layer and theme context.
 */
export function parseAllTokenFiles(tokensDir: string): RawCssToken[] {
  const files = readdirSync(tokensDir);
  const tokenFiles = files.filter(
    (f) =>
      f.startsWith(TOKEN_FILE_PREFIX) && f.endsWith(TOKEN_FILE_SUFFIX)
  );

  const allTokens: RawCssToken[] = [];

  for (const file of tokenFiles) {
    const filePath = `${tokensDir}/${file}`;
    const fileTokens = parseCssFile(filePath);
    allTokens.push(...fileTokens);
  }

  return allTokens;
}

/**
 * Parse a single CSS file and return its tokens.
 *
 * @param filePath - Absolute or relative path to a `tokens-*.css` file.
 * @returns Array of parsed tokens from the file.
 * @throws If the filename does not match `tokens-{layer}.css`.
 */
export function parseCssFile(filePath: string): RawCssToken[] {
  const filename = basename(filePath);
  const layer = layerFromFilename(filename);

  const raw = readFileSync(filePath, "utf-8");
  // Strip CSS comments before parsing to avoid false matches.
  const cleaned = raw.replace(COMMENT_RE, "");

  const tokens: RawCssToken[] = [];

  // Reset lastIndex since we reuse the global regex.
  SELECTOR_BLOCK_RE.lastIndex = 0;
  let blockMatch: RegExpExecArray | null;

  while ((blockMatch = SELECTOR_BLOCK_RE.exec(cleaned)) !== null) {
    const rawSelector = blockMatch[1];
    const blockBody = blockMatch[2];
    if (rawSelector === undefined || blockBody === undefined) continue;
    const selector = rawSelector.trim();

    // Skip non-selector blocks (e.g. media queries, @layer, @theme).
    if (!isValidTokenSelector(selector)) {
      continue;
    }

    const context = themeContextFromSelector(selector);

    DECLARATION_RE.lastIndex = 0;
    let declMatch: RegExpExecArray | null;

    while ((declMatch = DECLARATION_RE.exec(blockBody)) !== null) {
      const rawName = declMatch[1];
      const rawValue = declMatch[2];
      if (rawName === undefined || rawValue === undefined) continue;

      // Strip the `--` prefix from the property name.
      const name = rawName.slice(2);
      // Normalize whitespace in multi-line values (collapse runs of whitespace
      // into single spaces, trim leading/trailing).
      const value = rawValue.replace(/\s+/g, " ").trim();

      tokens.push({
        name,
        value,
        sourceFile: filename,
        selector,
        layer,
        context,
      });
    }
  }

  return tokens;
}

// ── Internal Helpers ─────────────────────────

/**
 * Check whether a CSS selector is a valid token-defining selector.
 *
 * We only extract tokens from:
 * - `:root`
 * - `[data-theme="..."]`
 * - `[data-domain="..."]`
 * - `[data-market-region="..."]`
 * - `[data-density="..."]`
 * - Compound selectors like `[data-theme="light"][data-domain="markets"]`
 *
 * We skip:
 * - `@theme`, `@layer`, `@import`, `@keyframes` etc. (at-rules)
 * - Element selectors, class selectors, pseudo-elements
 */
function isValidTokenSelector(selector: string): boolean {
  // Must be `:root` or start with `[` (attribute selector).
  if (selector === ":root") return true;
  if (selector.startsWith("[") && selector.endsWith("]")) return true;
  // Compound selectors like `[data-theme="light"][data-domain="markets"]`
  // start with `[` but end with `]` for the last attribute.
  if (selector.startsWith("[") && /\]\s*$/.test(selector)) return true;

  return false;
}
