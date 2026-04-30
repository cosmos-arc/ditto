#!/usr/bin/env bun
// ─────────────────────────────────────────────
// Ditto WCAG 2.1 Contrast Audit
// Checks all surface/text token pairs for AA compliance
// ─────────────────────────────────────────────

import {
  readAllTokenFiles,
  extractTokensFromCss,
  parseColorValue,
  resolveColor,
  contrastRatio,
  formatRatio,
  wcagLevel,
  emoji,
} from "./token-utils.mjs";

// ── Token pair definitions ──
// surface tokens (backgrounds) × text tokens (foregrounds)

const SURFACE_PATTERNS = [
  "surface-app",
  "surface-panel-base",
  "surface-panel-elevated",
  "surface-strip",
  "surface-overlay",
  "surface-modal",
  "surface-muted",
  "surface-elevated",
  "surface-frosted",
  "surface-frosted-subtle",
  "code-bg",
  "danger-subtle-bg",
];

const TEXT_PATTERNS = [
  "text-primary",
  "text-secondary",
  "text-tertiary",
  "text-quaternary",
  "text-disabled",
  "text-data-stale",
  "text-link",
  "text-link-hover",
  "text-error",
  "text-warning",
  "text-success",
  "code-text",
  "brand-accent-fg",
  "brand-signature-fg",
];

const TEXT_USAGE_TIERS = Object.freeze({
  "text-disabled": "decorative",
  "text-quaternary": "metadata",
  "text-data-stale": "operational",
  "text-tertiary": "metadata",
  "text-secondary": "operational",
});

const USAGE_TIER_GATES = Object.freeze({
  decorative: {
    failBelow: null,
    warnBelow: null,
    requiresNonColorMarker: false,
  },
  metadata: {
    failBelow: 3,
    warnBelow: 4.5,
    requiresNonColorMarker: false,
  },
  operational: {
    failBelow: 4.5,
    warnBelow: null,
    requiresNonColorMarker: false,
  },
  "data-critical": {
    failBelow: 4.5,
    warnBelow: null,
    requiresNonColorMarker: true,
  },
});

const BG_PATTERNS = ["overlay-2", "overlay-3", "overlay-4", "overlay-6", "overlay-8", "overlay-10", "overlay-12"];

// ── Build token map ──

function buildTokenMap() {
  const files = readAllTokenFiles();
  // Only use :root tokens (not theme overrides)
  let allCss = "";
  for (const { file, css } of files) {
    // Extract only :root block content
    const rootMatch = css.match(/:root\s*\{([^}]*)\}/s);
    if (rootMatch) {
      allCss += rootMatch[1] + "\n";
    }
  }
  const tokens = extractTokensFromCss(allCss);
  for (const [name, value] of Object.entries(tokens)) {
    tokens[`--${name}`] = value;
  }
  return tokens;
}

function resolveTokenValue(name, tokens) {
  return tokens[name] ?? tokens[name.replace(/^--/, "")] ?? tokens[`--${name}`];
}

function resolveAuditColor(value, tokens, seen = new Set()) {
  if (seen.has(value)) return null;
  seen.add(value);

  const color = resolveColor(value, tokens);
  if (color) return color;

  const parsed = parseColorValue(value);
  if (parsed.type === "var-fallback") {
    const resolved = resolveTokenValue(parsed.name, tokens);
    const resolvedColor = resolved ? resolveAuditColor(resolved, tokens, seen) : null;
    return resolvedColor ?? resolveAuditColor(parsed.fallback, tokens, seen);
  }

  if (parsed.type === "relative-oklch" && parsed.lMod === "l" && parsed.cMod === "c" && parsed.hMod === "h") {
    const base = resolveTokenValue(parsed.baseVar, tokens);
    if (!base) return null;
    const baseColor = resolveAuditColor(base, tokens, seen);
    if (!baseColor) return null;
    return {
      ...baseColor,
      alpha: parsed.alpha,
      isDerived: true,
    };
  }

  return null;
}

function getTextUsageTier(textName) {
  if (TEXT_USAGE_TIERS[textName]) return TEXT_USAGE_TIERS[textName];
  if (textName === "text-error" || textName === "text-warning" || textName === "text-success") {
    return "data-critical";
  }
  return "operational";
}

function classifyContrast(textName, ratio) {
  const usageTier = getTextUsageTier(textName);
  const gate = USAGE_TIER_GATES[usageTier];

  if (usageTier === "decorative") {
    return { usageTier, status: "report", pass: true, requiresNonColorMarker: gate.requiresNonColorMarker };
  }

  if (usageTier === "metadata") {
    if (ratio < gate.failBelow) return { usageTier, status: "fail", pass: false, requiresNonColorMarker: gate.requiresNonColorMarker };
    if (ratio < gate.warnBelow) return { usageTier, status: "warn", pass: true, requiresNonColorMarker: gate.requiresNonColorMarker };
    return { usageTier, status: "pass", pass: true, requiresNonColorMarker: gate.requiresNonColorMarker };
  }

  return {
    usageTier,
    status: ratio < gate.failBelow ? "fail" : "pass",
    pass: ratio >= gate.failBelow,
    requiresNonColorMarker: gate.requiresNonColorMarker,
  };
}

function updateCounts(classification, counts) {
  if (classification.status === "fail") counts.fail += 1;
  else if (classification.status === "warn") counts.warn += 1;
  else if (classification.status === "report") counts.report += 1;
  else counts.pass += 1;
}

function addUnresolved(unresolved, token, role, reason) {
  if (unresolved.some((entry) => entry.token === token && entry.role === role && entry.reason === reason)) return;
  unresolved.push({ token, role, reason });
}

// ── Main ──

function main() {
  const tokens = buildTokenMap();
  const results = [];
  const counts = {
    pass: 0,
    fail: 0,
    warn: 0,
    report: 0,
  };
  const unresolved = [];
  const skipped = [];

  // Surface × Text pairs
  for (const surfName of SURFACE_PATTERNS) {
    for (const textName of TEXT_PATTERNS) {
      const surfVal = tokens[surfName];
      const textVal = tokens[textName];
      if (!surfVal) {
        addUnresolved(unresolved, surfName, "surface", "token is declared for audit but missing from token map");
        continue;
      }
      if (!textVal) {
        addUnresolved(unresolved, textName, "text", "token is declared for audit but missing from token map");
        continue;
      }

      const surfColor = resolveAuditColor(surfVal, tokens);
      const textColor = resolveAuditColor(textVal, tokens);

      if (!surfColor) {
        addUnresolved(unresolved, surfName, "surface", `could not resolve ${surfVal}`);
        continue;
      }
      if (!textColor) {
        addUnresolved(unresolved, textName, "text", `could not resolve ${textVal}`);
        continue;
      }
      if (surfColor.alpha < 0.5) {
        if (!skipped.some((entry) => entry.token === surfName)) {
          skipped.push({ token: surfName, reason: `near-transparent background alpha ${surfColor.alpha.toFixed(2)}` });
        }
        continue;
      }

      const ratio = contrastRatio(surfColor.luminance, textColor.luminance);
      const level = wcagLevel(ratio);
      const classification = classifyContrast(textName, ratio);
      updateCounts(classification, counts);

      results.push({
        surface: surfName,
        text: textName,
        ratio,
        level,
        ...classification,
      });
    }
  }

  // Semi-transparent overlay × Text pairs
  for (const bgName of BG_PATTERNS) {
    for (const textName of ["text-primary", "text-secondary", "text-tertiary"]) {
      const bgVal = tokens[bgName];
      const textVal = tokens[textName];
      if (!bgVal) {
        addUnresolved(unresolved, bgName, "overlay", "token is declared for audit but missing from token map");
        continue;
      }
      if (!textVal) {
        addUnresolved(unresolved, textName, "text", "token is declared for audit but missing from token map");
        continue;
      }

      const bgColor = resolveAuditColor(bgVal, tokens);
      const textColor = resolveAuditColor(textVal, tokens);
      if (!bgColor) {
        addUnresolved(unresolved, bgName, "overlay", `could not resolve ${bgVal}`);
        continue;
      }
      if (!textColor) {
        addUnresolved(unresolved, textName, "text", `could not resolve ${textVal}`);
        continue;
      }

      // Effective luminance when overlay composited on surface-app
      const surfVal = tokens["surface-app"];
      if (!surfVal) {
        addUnresolved(unresolved, "surface-app", "surface", "overlay composite base is missing from token map");
        continue;
      }
      const surfColor = resolveAuditColor(surfVal, tokens);
      if (!surfColor) {
        addUnresolved(unresolved, "surface-app", "surface", `overlay composite base could not resolve ${surfVal}`);
        continue;
      }

      const alpha = bgColor.alpha;
      const effR = bgColor.rgb[0] * alpha + surfColor.rgb[0] * (1 - alpha);
      const effG = bgColor.rgb[1] * alpha + surfColor.rgb[1] * (1 - alpha);
      const effB = bgColor.rgb[2] * alpha + surfColor.rgb[2] * (1 - alpha);

      const effLum =
        0.2126 * ((effR <= 0.03928 ? effR / 12.92 : ((effR + 0.055) / 1.055) ** 2.4)) +
        0.7152 * ((effG <= 0.03928 ? effG / 12.92 : ((effG + 0.055) / 1.055) ** 2.4)) +
        0.0722 * ((effB <= 0.03928 ? effB / 12.92 : ((effB + 0.055) / 1.055) ** 2.4));

      const ratio = contrastRatio(effLum, textColor.luminance);
      const level = wcagLevel(ratio);
      const classification = classifyContrast(textName, ratio);
      updateCounts(classification, counts);

      results.push({
        surface: `${bgName} (on surface-app)`,
        text: textName,
        ratio,
        level,
        composited: true,
        ...classification,
      });
    }
  }

  // Sort: failures first, then warnings, then reports, then passes
  const statusOrder = { fail: 0, warn: 1, report: 2, pass: 3 };
  results.sort((a, b) => {
    if (a.status !== b.status) return statusOrder[a.status] - statusOrder[b.status];
    return a.ratio - b.ratio;
  });

  // ── Output ──

  console.log("\n## WCAG 2.1 Contrast Audit — Dark Mode (:root defaults)\n");
  console.log(`Pairs checked: ${results.length}`);
  console.log(
    `${emoji(7)} Pass: ${counts.pass}  ${emoji(3)} Warn: ${counts.warn}  ${emoji(1)} Fail: ${counts.fail + unresolved.length}  Report: ${counts.report}\n`,
  );

  if (unresolved.length > 0) {
    console.log("### Unresolved Audit Tokens\n");
    console.log("| Token | Role | Reason |");
    console.log("|-------|------|--------|");
    for (const entry of unresolved) {
      console.log(`| ${entry.token} | ${entry.role} | ${entry.reason} |`);
    }
    console.log("");
  }

  if (counts.fail > 0) {
    console.log("### Failed Pairs\n");
    console.log("| Surface | Text | Usage | Ratio | Level |");
    console.log("|---------|------|-------|-------|-------|");
    for (const r of results.filter((r) => r.status === "fail")) {
      console.log(`| ${r.surface} | ${r.text} | ${r.usageTier} | ${formatRatio(r.ratio)} | ${emoji(r.ratio)} ${r.level} |`);
    }
    console.log("");
  }

  if (skipped.length > 0) {
    console.log("### Excluded Transparent Backgrounds\n");
    console.log("| Token | Reason |");
    console.log("|-------|--------|");
    for (const entry of skipped) {
      console.log(`| ${entry.token} | ${entry.reason} |`);
    }
    console.log("");
  }

  if (counts.warn > 0) {
    console.log("### Warnings (metadata below 4.5:1)\n");
    console.log("| Surface | Text | Usage | Ratio | Level |");
    console.log("|---------|------|-------|-------|-------|");
    for (const r of results.filter((r) => r.status === "warn")) {
      console.log(`| ${r.surface} | ${r.text} | ${r.usageTier} | ${formatRatio(r.ratio)} | ${emoji(r.ratio)} ${r.level} |`);
    }
    console.log("");
  }

  if (counts.report > 0) {
    console.log("### Decorative Reports (non-gating)\n");
    console.log("| Surface | Text | Usage | Ratio | Level |");
    console.log("|---------|------|-------|-------|-------|");
    for (const r of results.filter((r) => r.status === "report")) {
      console.log(`| ${r.surface} | ${r.text} | ${r.usageTier} | ${formatRatio(r.ratio)} | ${emoji(r.ratio)} ${r.level} |`);
    }
    console.log("");
  }

  const dataCritical = results.filter((r) => r.usageTier === "data-critical");
  if (dataCritical.length > 0) {
    console.log("### Data-Critical Checked Pairs\n");
    console.log("| Surface | Text | Usage | Ratio | Level |");
    console.log("|---------|------|-------|-------|-------|");
    for (const r of dataCritical) {
      console.log(`| ${r.surface} | ${r.text} | ${r.usageTier} | ${formatRatio(r.ratio)} | ${emoji(r.ratio)} ${r.level} |`);
    }
    console.log("");
  }

  // Top 10 weakest passing pairs
  const passing = results.filter((r) => r.status === "pass" && r.level !== "AAA");
  if (passing.length > 0) {
    console.log("### Weakest Passing Pairs\n");
    console.log("| Surface | Text | Usage | Ratio | Level |");
    console.log("|---------|------|-------|-------|-------|");
    for (const r of passing.slice(0, 10)) {
      console.log(`| ${r.surface} | ${r.text} | ${r.usageTier} | ${formatRatio(r.ratio)} | ${emoji(r.ratio)} ${r.level} |`);
    }
    console.log("");
  }

  if (results.some((r) => r.requiresNonColorMarker)) {
    console.log("Data-critical text usage requires a non-color marker in UI contexts where status is conveyed.");
  }

  const totalFailures = counts.fail + unresolved.length;
  console.log(totalFailures === 0 ? "All gating pairs pass their contrast tier." : `${totalFailures} pair(s) fail contrast tier gates.`);

  const reportOnly = process.argv.includes("--report-only");
  process.exit(!reportOnly && totalFailures > 0 ? 1 : 0);
}

main();
