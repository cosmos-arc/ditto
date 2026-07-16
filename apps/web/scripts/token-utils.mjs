// ─────────────────────────────────────────────
// Ditto Design Token Utilities
// OKLCH parsing, CSS var extraction, WCAG contrast
// ─────────────────────────────────────────────

import { readFileSync, readdirSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const TOKENS_DIR = resolve(__dirname, "../src/styles/design-tokens");

// ── OKLCH → Linear sRGB → sRGB ──

export function oklchToRgb(L, C, H) {
  // oklch → oklab
  const hRad = (H * Math.PI) / 180;
  const a = C * Math.cos(hRad);
  const b = C * Math.sin(hRad);

  const l_ = L + 0.3963377774 * a + 0.2158037573 * b;
  const m = L + -0.1055613458 * a + -0.0638541728 * b;
  const s = L + -0.0894841775 * a + -1.2914855480 * b;

  const l3 = l_ * l_ * l_;
  const m3 = m * m * m;
  const s3 = s * s * s;

  let r = +4.0767416621 * l3 - 3.3077115913 * m3 + 0.2309699292 * s3;
  let g = -1.2684380046 * l3 + 2.6097574011 * m3 - 0.3413193965 * s3;
  let b2 = -0.0041960863 * l3 - 0.7034186147 * m3 + 1.7076147010 * s3;

  // Linear sRGB → sRGB (gamma decompress)
  const gamma = (c) =>
    c <= 0.0031308 ? 12.92 * c : 1.055 * c ** (1 / 2.4) - 0.055;

  return [gamma(clamp01(r)), gamma(clamp01(g)), gamma(clamp01(b2))];
}

function clamp01(v) {
  return v < 0 ? 0 : v > 1 ? 1 : v;
}

// ── WCAG 2.1 Relative Luminance ──

export function relativeLuminance(r, g, b) {
  const [rs, gs, bs] = [r, g, b].map((c) => {
    const s = c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
    return s;
  });
  return 0.2126 * rs + 0.7152 * gs + 0.0722 * bs;
}

export function contrastRatio(lum1, lum2) {
  const lighter = Math.max(lum1, lum2);
  const darker = Math.min(lum1, lum2);
  return (lighter + 0.05) / (darker + 0.05);
}

// ── Color Parsing ──

const OKLCH_RE =
  /oklch\(\s*([\d.]+%?)\s+([\d.]+)\s+([\d.]+)(?:\s*\/\s*([\d.]+))?\s*\)/;
const RELATIVE_OKLCH_RE =
  /oklch\(\s*from\s+var\(([^)]+)\)\s+([\w%]+)\s+([\w]+)\s+([\w]+)(?:\s*\/\s*([\d.]+))?\s*\)/;
const VAR_RE = /var\(([^)]+)\)/;

export function parseColorValue(rawValue) {
  const trimmed = rawValue.trim().replace(/;$/, "");

  // Direct OKLCH: oklch(0.5 0.1 235) or oklch(0.5 0.1 235 / 0.5)
  const oklch = trimmed.match(OKLCH_RE);
  if (oklch) {
    const L = oklch[1].endsWith("%") ? parseFloat(oklch[1]) / 100 : parseFloat(oklch[1]);
    const C = parseFloat(oklch[2]);
    const H = parseFloat(oklch[3]);
    const alpha = oklch[4] !== undefined ? parseFloat(oklch[4]) : 1;
    return { type: "oklch", L, C, H, alpha };
  }

  // Relative OKLCH: oklch(from var(--xxx) l c h / 0.5)
  const rel = trimmed.match(RELATIVE_OKLCH_RE);
  if (rel) {
    const baseVar = rel[1];
    const lMod = rel[2];
    const cMod = rel[3];
    const hMod = rel[4];
    const alpha = rel[5] !== undefined ? parseFloat(rel[5]) : 1;
    return { type: "relative-oklch", baseVar, lMod, cMod, hMod, alpha };
  }

  // var() reference: var(--brand-500)
  const varRef = trimmed.match(VAR_RE);
  if (varRef && varRef[0] === trimmed) {
    return { type: "var", name: varRef[1] };
  }

  // var() fallback: var(--surface-app-atmosphere, var(--neutral-0))
  const varFallback = trimmed.match(/^var\(([^,]+),\s*(.+)\)$/);
  if (varFallback) {
    return { type: "var-fallback", name: varFallback[1], fallback: varFallback[2].trim() };
  }

  return { type: "unknown", raw: trimmed };
}

export function resolveColor(value, allTokens) {
  const parsed = parseColorValue(value);

  switch (parsed.type) {
    case "oklch": {
      const [r, g, b] = oklchToRgb(parsed.L, parsed.C, parsed.H);
      return {
        rgb: [r, g, b],
        luminance: relativeLuminance(r, g, b),
        alpha: parsed.alpha,
        oklch: parsed,
      };
    }
    case "var": {
      const resolved = allTokens[parsed.name];
      if (!resolved) return null;
      return resolveColor(resolved, allTokens);
    }
    case "var-fallback": {
      const resolved = allTokens[parsed.name];
      if (resolved) return resolveColor(resolved, allTokens);
      return resolveColor(parsed.fallback, allTokens);
    }
    case "relative-oklch": {
      const base = allTokens[parsed.baseVar];
      if (!base) return null;
      const baseParsed = parseColorValue(base);
      if (baseParsed.type !== "oklch") return null;
      const [r, g, b] = oklchToRgb(baseParsed.L, baseParsed.C, baseParsed.H);
      return {
        rgb: [r, g, b],
        luminance: relativeLuminance(r, g, b),
        alpha: parsed.alpha,
        oklch: baseParsed,
        isDerived: true,
      };
    }
    default:
      return null;
  }
}

// ── CSS Token Extraction ──

export function extractTokensFromCss(cssText) {
  const tokens = {};
  // Match --name: value; patterns
  const blockRe = /(?:^|\n)\s*--([a-zA-Z0-9_-]+)\s*:\s*([^;}\n]+)/g;
  let match;
  while ((match = blockRe.exec(cssText)) !== null) {
    const name = match[1];
    const value = match[2].trim();
    tokens[name] = value;
  }
  return tokens;
}

export function extractAllVarReferences(cssText) {
  const refs = new Set();
  const re = /var\(([^)]+)\)/g;
  let match;
  while ((match = re.exec(cssText)) !== null) {
    refs.add(match[1]);
  }
  return refs;
}

export function extractAllTokenDeclarations(cssText) {
  const decls = new Set();
  const re = /(?:^|\n)\s*--([a-zA-Z0-9_-]+)\s*:/g;
  let match;
  while ((match = re.exec(cssText)) !== null) {
    decls.add(`--${match[1]}`);
  }
  return decls;
}

export function getTokenFiles() {
  return readdirSync(TOKENS_DIR)
    .filter((f) => f.startsWith("tokens-") && f.endsWith(".css"))
    .sort();
}

export function readAllTokenFiles() {
  const files = getTokenFiles();
  const allCss = files.map((f) => {
    const path = resolve(TOKENS_DIR, f);
    return { file: f, css: readFileSync(path, "utf-8") };
  });
  return allCss;
}

// ── Reporting Helpers ──

export function formatRatio(ratio) {
  return `${ratio.toFixed(2)}:1`;
}

export function wcagLevel(ratio) {
  if (ratio >= 7) return "AAA";
  if (ratio >= 4.5) return "AA";
  if (ratio >= 3) return "AA Large";
  return "FAIL";
}

export function emoji(ratio) {
  if (ratio >= 7) return "✅";
  if (ratio >= 4.5) return "✅";
  if (ratio >= 3) return "⚠️";
  return "❌";
}
