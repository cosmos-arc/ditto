/**
 * Token Audit Script
 *
 * 提取 Stitch 原型中的设计值，与 Token v2 对比，生成审计报告。
 * 用法: bun run scripts/audit-tokens.mjs
 */

import { readFileSync, writeFileSync, readdirSync } from "node:fs";
import { join, basename } from "node:path";
import { findHardcodedColors } from "./prototype-color-audit.ts";

// ─── OKLCH → sRGB → Hex Conversion ───────────────────────────────────────────
// Based on CSS Color Level 4 specification.

function oklchToLab(l, c, h) {
  const hRad = ((h ?? 0) / 360) * Math.PI * 2;
  return [l, c * Math.cos(hRad), c * Math.sin(hRad)];
}

function labToXyz(l, a, b) {
  const f = (t) => {
    const delta = 6 / 29;
    return t > delta ? t ** 3 : (116 * t - 16) / 3 * (3 * delta * delta);
  };
  const fy = (l + 16) / 116;
  const fx = a / 500 + fy;
  const fz = fy - b / 200;
  const x = 0.95047 * f(fx);
  const y = 1.00000 * f(fy);
  const z = 1.08883 * f(fz);
  return [x, y, z];
}

function xyzToLinearRgb(x, y, z) {
  return [
    +3.2404542 * x - 1.5371385 * y - 0.4985314 * z,
    -0.969266 * x + 1.8760108 * y + 0.041556 * z,
    +0.0556434 * x - 0.2040259 * y + 1.0572252 * z,
  ];
}

function srgbTransfer(c) {
  return c <= 0.0031308
    ? 12.92 * c
    : 1.055 * c ** (1 / 2.4) - 0.055;
}

function linearRgbToSrgb(r, g, b) {
  return [
    srgbTransfer(r),
    srgbTransfer(g),
    srgbTransfer(b),
  ];
}

function oklchToHex(l, c, h) {
  const [labL, labA, labB] = oklchToLab(l, c, h);
  const [x, y, z] = labToXyz(labL, labA, labB);
  const [lr, lg, lb] = xyzToLinearRgb(x, y, z);
  const [sr, sg, sb] = linearRgbToSrgb(lr, lg, lb);
  const clamp = (v) => Math.max(0, Math.min(1, v));
  const toHex = (v) => Math.round(clamp(v) * 255).toString(16).padStart(2, "0");
  return `#${toHex(sr)}${toHex(sg)}${toHex(sb)}`.toUpperCase();
}

function parseOklch(str) {
  const match = str.match(
    /oklch\(\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)\s*\)/,
  );
  if (!match) return null;
  return {
    l: Number.parseFloat(match[1]),
    c: Number.parseFloat(match[2]),
    h: Number.parseFloat(match[3]),
  };
}

// ─── Config ───────────────────────────────────────────────────────────────────

const PROTOTYPES_DIR = "docs/designs/stitch";
const TOKENS_DIR = "src/styles/tokens";
const OUTPUT_PATH = "docs/plans/audit-raw-data.json";

// ─── Helpers ──────────────────────────────────────────────────────────────────

function extractHexValues(html) {
  const values = new Set();
  for (const color of findHardcodedColors(html)) {
    if (!color.startsWith("#")) continue;

    const hex = normalizeHex(color);
    if (hex) values.add(hex);
  }
  return [...values].sort();
}

function normalizeHex(hexStr) {
  let hex = hexStr.replace(/^#/, "");
  if (hex.length === 3) {
    hex = hex
      .split("")
      .map((c) => c + c)
      .join("");
  }
  if (hex.length === 6 || hex.length === 8) {
    return `#${hex.slice(0, 6).toUpperCase()}`;
  }
  return null;
}

function hexToRgb(hex) {
  const h = hex.replace("#", "");
  return {
    r: Number.parseInt(h.slice(0, 2), 16),
    g: Number.parseInt(h.slice(2, 4), 16),
    b: Number.parseInt(h.slice(4, 6), 16),
  };
}

function colorDistance(hex1, hex2) {
  const c1 = hexToRgb(hex1);
  const c2 = hexToRgb(hex2);
  const dr = c1.r - c2.r;
  const dg = c1.g - c2.g;
  const db = c1.b - c2.b;
  return Math.sqrt(dr * dr + dg * dg + db * db);
}

function extractTailwindConfig(html) {
  const configMatch = html.match(
    /tailwind\.config\s*=\s*(\{[\s\S]*?\});?\s*<\/script>/,
  );
  if (!configMatch) return null;
  try {
    // Simple extraction - not a full JSON parser
    const configStr = configMatch[1];
    return configStr;
  } catch {
    return null;
  }
}

function extractCssVariables(html) {
  const vars = [];
  const regex = /--([\w-]+)\s*:\s*([^;]+);/g;
  let match;
  while ((match = regex.exec(html)) !== null) {
    vars.push({
      name: match[1],
      value: match[2].trim(),
      full: match[0].trim(),
    });
  }
  return vars;
}

function extractFontFamilies(html) {
  const families = new Set();
  // From Google Fonts links
  const fontLinks = html.match(/fonts\.googleapis\.com[^"']+family=([^"']+)/g);
  if (fontLinks) {
    for (const link of fontLinks) {
      const familyMatch = link.match(/family=([^&:]+)/g);
      if (familyMatch) {
        for (const f of familyMatch) {
          families.add(f.replace("family=", "").replace(/\+/g, " "));
        }
      }
    }
  }
  // From CSS font-family declarations
  const fontFamilyRegex = /font-family\s*:\s*([^;}"']+)/g;
  let match;
  while ((match = fontFamilyRegex.exec(html)) !== null) {
    const fonts = match[1].split(",").map((f) => f.trim().replace(/['"]/g, ""));
    for (const f of fonts) {
      if (f !== "sans-serif" && f !== "monospace" && f !== "serif") {
        families.add(f);
      }
    }
  }
  return [...families];
}

function extractArbitrarySizes(html) {
  const sizes = new Set();
  // Tailwind arbitrary values for size: text-[11px], h-[48px], w-[240px], gap-0.5, etc.
  const arbitrarySizeRegex =
    /(?:text|w|h|min-w|max-w|min-h|max-h|gap|p|px|py|pt|pb|pl|pr|m|mx|my|mt|mb|ml|mr|rounded|space)-(?:\[([^\]]+)\]|([\d.]+))/g;
  let match;
  while ((match = arbitrarySizeRegex.exec(html)) !== null) {
    sizes.add(match[1] || match[2]);
  }
  return [...sizes].sort();
}

function extractBorderRadius(html) {
  const radii = new Set();
  const regex =
    /(?:rounded|border-radius)\s*(?:\[([^\]]+)\]|(\w+))/g;
  let match;
  while ((match = regex.exec(html)) !== null) {
    const val = match[1] || match[2];
    if (val && val !== "none" && val !== "full") {
      radii.add(val);
    }
  }
  // Also from CSS
  const cssRadiusRegex = /border-radius\s*:\s*([^;]+)/g;
  while ((match = cssRadiusRegex.exec(html)) !== null) {
    radii.add(match[1].trim());
  }
  // From Tailwind config
  const configRadiusRegex = /borderRadius\s*:\s*\{([^}]+)\}/;
  const configMatch = html.match(configRadiusRegex);
  if (configMatch) {
    const inner = configMatch[1];
    const entries = inner.match(/["']?(\w+)["']?\s*:\s*["']?([^"'}]+)["']?/g);
    if (entries) {
      for (const entry of entries) {
        const [, name, value] = entry.match(
          /["']?(\w+)["']?\s*:\s*["']?([^"'}]+)["']?/,
        );
        radii.add(`${name}: ${value}`);
      }
    }
  }
  return [...radii].sort();
}

function extractBoxShadows(html) {
  const shadows = new Set();
  const regex = /box-shadow\s*:\s*([^;]+)/g;
  let match;
  while ((match = regex.exec(html)) !== null) {
    shadows.add(match[1].trim());
  }
  // Also Tailwind shadow classes
  const twShadowRegex = /shadow-(\w+)/g;
  while ((match = twShadowRegex.exec(html)) !== null) {
    shadows.add(match[1]);
  }
  return [...shadows].sort();
}

function extractTransitions(html) {
  const transitions = new Set();
  const regex = /(?:transition|animation|duration)-(\w+)/g;
  let match;
  while ((match = regex.exec(html)) !== null) {
    transitions.add(match[1]);
  }
  // From CSS
  const cssTransitionRegex = /transition\s*:\s*([^;]+)/g;
  while ((match = cssTransitionRegex.exec(html)) !== null) {
    transitions.add(match[1].trim());
  }
  // From Tailwind config
  const configTransRegex = /transitionDuration\s*:\s*\{([^}]+)\}/;
  const configMatch = html.match(configTransRegex);
  if (configMatch) {
    transitions.add(`config: ${configMatch[1].trim()}`);
  }
  return [...transitions].sort();
}

function extractSpacingTokens(css) {
  const tokens = [];
  const regex = /--spacing-(\w+)\s*:\s*([^;]+);/g;
  let match;
  while ((match = regex.exec(css)) !== null) {
    tokens.push({ name: match[1], value: match[2].trim() });
  }
  return tokens;
}

function extractRadiusTokens(css) {
  const tokens = [];
  const regex = /--radius-(\w+)\s*:\s*([^;]+);/g;
  let match;
  while ((match = regex.exec(css)) !== null) {
    tokens.push({ name: match[1], value: match[2].trim() });
  }
  return tokens;
}

function extractShadowTokens(css) {
  const tokens = [];
  const regex = /--shadow-(\w+)\s*:\s*([^;]+);/g;
  let match;
  while ((match = regex.exec(css)) !== null) {
    tokens.push({ name: match[1], value: match[2].trim() });
  }
  return tokens;
}

function extractMotionTokens(css) {
  const tokens = [];
  const durationRegex = /--duration-(\w+)\s*:\s*([^;]+);/g;
  let match;
  while ((match = durationRegex.exec(css)) !== null) {
    tokens.push({ type: "duration", name: match[1], value: match[2].trim() });
  }
  const easingRegex = /--ease-(\w+)\s*:\s*([^;]+);/g;
  while ((match = easingRegex.exec(css)) !== null) {
    tokens.push({ type: "easing", name: match[1], value: match[2].trim() });
  }
  return tokens;
}

function extractColorTokens(css) {
  const tokens = [];
  const regex = /--(color-[\w-]+)\s*:\s*([^;]+);/g;
  let match;
  while ((match = regex.exec(css)) !== null) {
    const name = match[1];
    const value = match[2].trim();
    tokens.push({ name, value });
  }
  return tokens;
}

function extractTypographyTokens(css) {
  const tokens = [];
  const sizeRegex = /--font-size-(\w+)\s*:\s*([^;]+);/g;
  let match;
  while ((match = sizeRegex.exec(css)) !== null) {
    tokens.push({ type: "size", name: match[1], value: match[2].trim() });
  }
  const weightRegex = /--font-weight-(\w+)\s*:\s*([^;]+);/g;
  while ((match = weightRegex.exec(css)) !== null) {
    tokens.push({ type: "weight", name: match[1], value: match[2].trim() });
  }
  const familyRegex = /--font-(sans|mono)\s*:\s*([^;]+);/g;
  while ((match = familyRegex.exec(css)) !== null) {
    tokens.push({ type: "family", name: match[1], value: match[2].trim() });
  }
  return tokens;
}

// ─── Extract Token v2 Reference ──────────────────────────────────────────────

function buildTokenReference(tokensDir) {
  const ref = {
    colors: {},
    spacing: {},
    radius: {},
    shadows: {},
    motion: {},
    typography: {},
  };

  // Primitives
  const primitives = readFileSync(join(tokensDir, "primitives.css"), "utf-8");
  ref.colors.primitives = extractColorTokens(primitives);
  ref.spacing = extractSpacingTokens(primitives);
  ref.radius = extractRadiusTokens(primitives);
  ref.shadows = extractShadowTokens(primitives);

  // Semantic Core
  const core = readFileSync(join(tokensDir, "semantic-core.css"), "utf-8");
  ref.colors.semanticCore = extractColorTokens(core);

  // Domain tokens
  const domainFiles = [
    "semantic-market",
    "semantic-risk",
    "semantic-execution",
    "semantic-system",
    "semantic-data",
    "semantic-model",
  ];
  ref.colors.domains = {};
  for (const domain of domainFiles) {
    const filePath = join(tokensDir, `${domain}.css`);
    try {
      const css = readFileSync(filePath, "utf-8");
      ref.colors.domains[domain] = extractColorTokens(css);
    } catch {
      ref.colors.domains[domain] = [];
    }
  }

  // Component tokens
  try {
    const components = readFileSync(
      join(tokensDir, "components.css"),
      "utf-8",
    );
    ref.colors.components = extractColorTokens(components);
  } catch {
    ref.colors.components = [];
  }

  // Chart tokens
  try {
    const charts = readFileSync(join(tokensDir, "charts.css"), "utf-8");
    ref.colors.charts = extractColorTokens(charts);
  } catch {
    ref.colors.charts = [];
  }

  // Grid tokens
  try {
    const grid = readFileSync(join(tokensDir, "grid.css"), "utf-8");
    ref.colors.grid = extractColorTokens(grid);
  } catch {
    ref.colors.grid = [];
  }

  // Typography
  try {
    const typo = readFileSync(join(tokensDir, "typography.css"), "utf-8");
    ref.typography = extractTypographyTokens(typo);
  } catch {
    ref.typography = [];
  }

  // Motion
  try {
    const motion = readFileSync(join(tokensDir, "motion.css"), "utf-8");
    ref.motion = extractMotionTokens(motion);
  } catch {
    ref.motion = [];
  }

  return ref;
}

// ─── Find Prototype Directories ──────────────────────────────────────────────

function findPrototypeDirs(baseDir) {
  const entries = readdirSync(baseDir, { withFileTypes: true });
  return entries
    .filter((e) => e.isDirectory())
    .map((e) => e.name)
    .sort();
}

// ─── Main ────────────────────────────────────────────────────────────────────

function main() {
  console.log("=== Ditto Token Audit ===\n");

  // Build token reference
  console.log("1. Building Token v2 reference...");
  const tokenRef = buildTokenReference(TOKENS_DIR);

  // Count tokens
  const colorCount =
    (tokenRef.colors.primitives?.length || 0) +
    (tokenRef.colors.semanticCore?.length || 0) +
    Object.values(tokenRef.colors.domains || {}).reduce(
      (sum, arr) => sum + arr.length,
      0,
    ) +
    (tokenRef.colors.components?.length || 0) +
    (tokenRef.colors.charts?.length || 0) +
    (tokenRef.colors.grid?.length || 0);
  console.log(
    `   Colors: ${colorCount} tokens (${tokenRef.colors.primitives?.length || 0} primitive, ${tokenRef.colors.semanticCore?.length || 0} semantic core, ${Object.values(tokenRef.colors.domains || {}).reduce((s, a) => s + a.length, 0)} domain)`,
  );
  console.log(`   Spacing: ${tokenRef.spacing.length} tokens`);
  console.log(`   Radius: ${tokenRef.radius.length} tokens`);
  console.log(`   Shadows: ${tokenRef.shadows.length} tokens`);
  console.log(`   Motion: ${tokenRef.motion.length} tokens`);
  console.log(`   Typography: ${tokenRef.typography.length} tokens`);

  // Find prototypes
  console.log("\n2. Scanning prototypes...");
  const protoDirs = findPrototypeDirs(PROTOTYPES_DIR);
  console.log(`   Found ${protoDirs.length} prototypes: ${protoDirs.join(", ")}`);

  // Audit each prototype
  const auditResults = {};
  for (const dir of protoDirs) {
    const htmlPath = join(PROTOTYPES_DIR, dir, "code.html");
    let html;
    try {
      html = readFileSync(htmlPath, "utf-8");
    } catch {
      console.log(`   WARNING: No code.html in ${dir}, skipping`);
      continue;
    }

    console.log(`\n   Auditing ${dir}...`);

    const result = {
      filePath: htmlPath,
      lineCount: html.split("\n").length,
      hexColors: extractHexValues(html),
      cssVariables: extractCssVariables(html),
      fontFamilies: extractFontFamilies(html),
      arbitrarySizes: extractArbitrarySizes(html),
      borderRadius: extractBorderRadius(html),
      boxShadow: extractBoxShadows(html),
      transitions: extractTransitions(html),
      tailwindConfig: extractTailwindConfig(html),
    };

    auditResults[dir] = result;
    console.log(`     Hex colors: ${result.hexColors.length}`);
    console.log(`     CSS variables: ${result.cssVariables.length}`);
    console.log(`     Font families: ${result.fontFamilies.join(", ")}`);
    console.log(`     Lines: ${result.lineCount}`);
  }

  // Build hex-to-token mapping from ALL token layers
  console.log("\n3. Building hex-to-token mapping (OKLCH → hex)...");
  const hexToTokens = new Map();

  function addTokenMapping(token) {
    const oklch = parseOklch(token.value);
    if (!oklch) return;
    const hex = oklchToHex(oklch.l, oklch.c, oklch.h);
    if (!hexToTokens.has(hex)) hexToTokens.set(hex, []);
    hexToTokens.get(hex).push(token.name);
  }

  // All color token layers
  for (const token of tokenRef.colors.primitives || []) addTokenMapping(token);
  for (const token of tokenRef.colors.semanticCore || []) addTokenMapping(token);
  for (const tokens of Object.values(tokenRef.colors.domains || {})) {
    for (const token of tokens) addTokenMapping(token);
  }
  for (const token of tokenRef.colors.components || []) addTokenMapping(token);
  for (const token of tokenRef.colors.charts || []) addTokenMapping(token);
  for (const token of tokenRef.colors.grid || []) addTokenMapping(token);

  console.log(`   Mapped ${hexToTokens.size} unique hex values to tokens`);

  // Match prototype hex values to nearest tokens
  console.log("\n4. Matching prototype colors to tokens...");
  const allTokenHexes = [...hexToTokens.keys()];
  for (const [dir, result] of Object.entries(auditResults)) {
    result.colorMatches = [];
    for (const hex of result.hexColors) {
      // Exact match
      if (hexToTokens.has(hex)) {
        result.colorMatches.push({
          prototypeHex: hex,
          matchType: "exact",
          tokens: hexToTokens.get(hex),
          distance: 0,
        });
      } else {
        // Find nearest
        let nearest = null;
        let minDist = Infinity;
        for (const tokenHex of allTokenHexes) {
          const dist = colorDistance(hex, tokenHex);
          if (dist < minDist) {
            minDist = dist;
            nearest = tokenHex;
          }
        }
        result.colorMatches.push({
          prototypeHex: hex,
          matchType: minDist < 10 ? "near" : "none",
          nearestTokenHex: nearest,
          tokens: nearest ? hexToTokens.get(nearest) : [],
          distance: Math.round(minDist * 10) / 10,
        });
      }
    }

    // Count matches
    const exact = result.colorMatches.filter((m) => m.matchType === "exact").length;
    const near = result.colorMatches.filter((m) => m.matchType === "near").length;
    const none = result.colorMatches.filter((m) => m.matchType === "none").length;
    console.log(`   ${dir}: ${exact} exact, ${near} near, ${none} unmatched`);
  }

  // Write raw data
  const output = {
    timestamp: new Date().toISOString(),
    tokenReference: {
      colorCount,
      spacingCount: tokenRef.spacing.length,
      radiusCount: tokenRef.radius.length,
      shadowCount: tokenRef.shadows.length,
      motionCount: tokenRef.motion.length,
      typographyCount: tokenRef.typography.length,
    },
    prototypes: auditResults,
  };

  writeFileSync(OUTPUT_PATH, JSON.stringify(output, null, 2));
  console.log(`\n5. Raw data written to ${OUTPUT_PATH}`);
  console.log("=== Audit Complete ===");
}

main();
