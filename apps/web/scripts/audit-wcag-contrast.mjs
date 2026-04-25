#!/usr/bin/env bun
// ─────────────────────────────────────────────
// Ditto WCAG 2.1 Contrast Audit
// Checks all surface/text token pairs for AA compliance
// ─────────────────────────────────────────────

import {
  readAllTokenFiles,
  extractTokensFromCss,
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
  "text-inverse",
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
  return extractTokensFromCss(allCss);
}

// ── Main ──

function main() {
  const tokens = buildTokenMap();
  const results = [];
  let passCount = 0;
  let failCount = 0;
  let warnCount = 0;

  // Surface × Text pairs
  for (const surfName of SURFACE_PATTERNS) {
    for (const textName of TEXT_PATTERNS) {
      const surfVal = tokens[surfName];
      const textVal = tokens[textName];
      if (!surfVal || !textVal) continue;

      const surfColor = resolveColor(surfVal, tokens);
      const textColor = resolveColor(textVal, tokens);

      if (!surfColor || !textColor) continue;
      if (surfColor.alpha < 0.5) continue; // skip near-transparent backgrounds

      const ratio = contrastRatio(surfColor.luminance, textColor.luminance);
      const level = wcagLevel(ratio);
      const isFail = !level.startsWith("AA") && !level.startsWith("AAA");
      const isWarn = level === "AA Large";

      if (isFail) failCount++;
      else if (isWarn) warnCount++;
      else passCount++;

      results.push({
        surface: surfName,
        text: textName,
        ratio,
        level,
        pass: !isFail,
      });
    }
  }

  // Semi-transparent overlay × Text pairs
  for (const bgName of BG_PATTERNS) {
    for (const textName of ["text-primary", "text-secondary", "text-tertiary"]) {
      const bgVal = tokens[bgName];
      const textVal = tokens[textName];
      if (!bgVal || !textVal) continue;

      const bgColor = resolveColor(bgVal, tokens);
      const textColor = resolveColor(textVal, tokens);
      if (!bgColor || !textColor) continue;

      // Effective luminance when overlay composited on surface-app
      const surfVal = tokens["surface-app"];
      if (!surfVal) continue;
      const surfColor = resolveColor(surfVal, tokens);
      if (!surfColor) continue;

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
      const isFail = !level.startsWith("AA") && !level.startsWith("AAA");
      const isWarn = level === "AA Large";

      if (isFail) failCount++;
      else if (isWarn) warnCount++;
      else passCount++;

      results.push({
        surface: `${bgName} (on ${surfName})`,
        text: textName,
        ratio,
        level,
        pass: !isFail,
        composited: true,
      });
    }
  }

  // Sort: failures first, then warnings, then passes
  results.sort((a, b) => {
    if (a.pass !== b.pass) return a.pass ? 1 : -1;
    return a.ratio - b.ratio;
  });

  // ── Output ──

  console.log("\n## WCAG 2.1 Contrast Audit — Dark Mode (:root defaults)\n");
  console.log(`Pairs checked: ${results.length}`);
  console.log(`${emoji(7)} Pass: ${passCount}  ${emoji(3)} Warn: ${warnCount}  ${emoji(1)} Fail: ${failCount}\n`);

  if (failCount > 0) {
    console.log("### Failed Pairs (< 3:1)\n");
    console.log("| Surface | Text | Ratio | Level |");
    console.log("|---------|------|-------|-------|");
    for (const r of results.filter((r) => !r.pass)) {
      console.log(`| ${r.surface} | ${r.text} | ${formatRatio(r.ratio)} | ${emoji(r.ratio)} ${r.level} |`);
    }
    console.log("");
  }

  if (warnCount > 0) {
    console.log("### Warnings (AA Large only, 3:1–4.5:1)\n");
    console.log("| Surface | Text | Ratio | Level |");
    console.log("|---------|------|-------|-------|");
    for (const r of results.filter((r) => r.pass && r.level === "AA Large")) {
      console.log(`| ${r.surface} | ${r.text} | ${formatRatio(r.ratio)} | ${emoji(r.ratio)} ${r.level} |`);
    }
    console.log("");
  }

  // Top 10 weakest passing pairs
  const passing = results.filter((r) => r.pass && r.level !== "AA Large" && r.level !== "AAA");
  if (passing.length > 0) {
    console.log("### Weakest Passing Pairs\n");
    console.log("| Surface | Text | Ratio | Level |");
    console.log("|---------|------|-------|-------|");
    for (const r of passing.slice(0, 10)) {
      console.log(`| ${r.surface} | ${r.text} | ${formatRatio(r.ratio)} | ${emoji(r.ratio)} ${r.level} |`);
    }
    console.log("");
  }

  console.log(failCount === 0 ? "All pairs pass WCAG AA." : `${failCount} pair(s) fail WCAG AA.`);

  // Exit 0 always — this is an informational audit tool.
  // Use --ci flag to exit 1 on failures (for CI gating).
  const isCI = process.argv.includes("--ci");
  process.exit(isCI && failCount > 0 ? 1 : 0);
}

main();
