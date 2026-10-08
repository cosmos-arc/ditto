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
  "brand-signature-fg",
];
// brand-accent-fg 是 on-accent 按钮白字（配 --brand-accent 蓝底），不是
// on-surface 文本——从 surface 对集移除，改由 BADGE_COMBOS 的 accent 对守护。

const TEXT_USAGE_TIERS = Object.freeze({
  "text-disabled": "decorative",
  "text-quaternary": "metadata",
  "text-data-stale": "operational",
  "text-tertiary": "metadata",
  "text-secondary": "operational",
  // 弱化状态（平盘/已取消）视觉意图即弱于常规操作文本（#555 裁决留档）
  "market-flat-fg": "metadata",
  "execution-cancelled-fg": "metadata",
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
  badge: {
    failBelow: 3,
    warnBelow: 4.5,
    requiresNonColorMarker: false,
  },
});

const BG_PATTERNS = ["overlay-2", "overlay-3", "overlay-4", "overlay-6", "overlay-8", "overlay-10", "overlay-12"];

// Domain/LED fg tokens audited against the two primary surfaces in BOTH themes (#555:
// 此前 domain fg 不在对集——dark 亦未守护，light 校准值首次获得门禁覆盖)。
const DOMAIN_FG_PATTERNS = [
  "market-up-fg",
  "market-down-fg",
  "market-flat-fg",
  "market-strong-fg",
  "market-weak-fg",
  "risk-low-fg",
  "risk-medium-fg",
  "risk-high-fg",
  "risk-critical-fg",
  "risk-near-limit-fg",
  "risk-breach-fg",
  "execution-pending-fg",
  "execution-partial-fg",
  "execution-filled-fg",
  "execution-rejected-fg",
  "execution-cancelled-fg",
  "system-healthy-fg",
  "system-degraded-fg",
  "system-stale-fg",
  "system-down-fg",
  "data-quality-fresh-fg",
  "data-quality-delayed-fg",
  "data-quality-missing-fg",
  "model-stable-fg",
  "model-degrading-fg",
  "model-drifting-fg",
  "model-invalid-fg",
  "agent-running-fg",
  "agent-failed-fg",
  "status-led-healthy",
  "status-led-degraded",
  "status-led-warning",
  "status-led-critical",
  "status-led-live",
  "status-led-idle",
  "status-led-error",
  "status-led-info",
];
const DOMAIN_FG_SURFACES = ["surface-app", "surface-panel-base"];

// 同色系淡底徽章组合（fg on its α-tint bg composited over panel-base）。
// #555 裁决：badge 按 UI 组件级 3:1 gate（WCAG 1.4.11）——状态徽章有
// border/bg/text 三重编码；4.5 以上记 pass，3–4.5 记 warn 提示。
const BADGE_COMBOS = [
  ["status-led-critical", "risk-critical-bg"],
  ["status-led-warning", "risk-medium-bg"],
  ["status-led-info", "execution-partial-bg"],
  ["execution-filled-fg", "execution-filled-bg"],
  ["system-healthy-fg", "system-healthy-bg"],
  ["risk-medium-fg", "risk-medium-bg"],
  ["risk-critical-fg", "risk-critical-bg"],
  ["market-up-fg", "market-up-bg"],
  ["market-down-fg", "market-down-bg"],
  // accent 按钮前景：白字配 brand-accent 蓝底（不透明 α=1），同按 UI 组件级
  // 3:1 裁决（dark 3.20 / light 4.63，按钮形状+底色多重编码）
  ["brand-accent-fg", "brand-accent"],
];

// Chart Cockpit series tokens audited against the chart pane surface in BOTH themes.
// 涨跌 up/down 在 intl 市场配色下互为同值换位，对比度等价，不重复设对。
const CHART_SERIES_PATTERNS = [
  "chart-series-up",
  "chart-series-down",
  "chart-series-neutral",
  "chart-combo-model",
  "chart-combo-paper",
  "chart-combo-manual",
  "chart-run-1",
  "chart-run-2",
  "chart-run-3",
  "chart-run-4",
  "chart-run-5",
  "chart-run-6",
  "chart-run-7",
  "chart-run-8",
  "chart-quantile-1",
  "chart-quantile-2",
  "chart-quantile-3",
  "chart-quantile-4",
  "chart-quantile-5",
  "chart-ls-spread",
];
const CHART_SURFACE = "chart-bg";

const STATIC_AUDIT_TOKEN_VALUES = Object.freeze({
  // Atmosphere defaults all runtime offsets to zero, so the static audit uses the base app surface.
  "surface-app-atmosphere": "var(--neutral-0)",
});

// ── Build token map ──

function extractBlocks(css, selector) {
  // Plain-selector blocks only: compound selectors like `[data-theme="light"][data-domain="…"]`
  // carry narrower semantics and are intentionally not merged into the theme overlay.
  const pattern = new RegExp(`${selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\s*\\{([^}]*)\\}`, "g");
  let combined = "";
  for (const match of css.matchAll(pattern)) {
    combined += `${match[1]}\n`;
  }
  return combined;
}

function buildTokenMap(theme = "dark") {
  const files = readAllTokenFiles();
  let allCss = "";
  let themeCss = "";
  for (const { css } of files) {
    allCss += extractBlocks(css, ":root");
    if (theme === "light") {
      // extractBlocks escapes the selector itself — pass the RAW selector.
      // （历史 bug：此处曾传已转义的 \[data-theme="light"\]，双重转义使
      // light 覆写从未进入 token map，chart「双主题」段实际审计了两遍 dark。）
      themeCss += extractBlocks(css, '[data-theme="light"]');
    }
  }
  const tokens = extractTokensFromCss(allCss + (theme === "light" ? themeCss : ""));
  for (const [name, value] of Object.entries(STATIC_AUDIT_TOKEN_VALUES)) {
    tokens[name] = value;
  }
  for (const [name, value] of Object.entries(tokens)) {
    tokens[`--${name}`] = value;
  }
  return tokens;
}

function resolveTokenValue(name, tokens) {
  return tokens[name] ?? tokens[name.replace(/^--/, "")] ?? tokens[`--${name}`];
}

function parseAuditVar(value) {
  const trimmed = value.trim();
  if (!trimmed.startsWith("var(") || !trimmed.endsWith(")")) return null;

  const inner = trimmed.slice(4, -1);
  let depth = 0;
  for (let i = 0; i < inner.length; i += 1) {
    const char = inner[i];
    if (char === "(") depth += 1;
    else if (char === ")") depth -= 1;
    else if (char === "," && depth === 0) {
      return {
        name: inner.slice(0, i).trim(),
        fallback: inner.slice(i + 1).trim(),
      };
    }
  }

  return {
    name: inner.trim(),
    fallback: null,
  };
}

function resolveAuditColor(value, tokens, seen = new Set()) {
  if (seen.has(value)) return null;
  seen.add(value);

  const auditVar = parseAuditVar(value);
  if (auditVar) {
    const resolved = resolveTokenValue(auditVar.name, tokens);
    if (resolved) return resolveAuditColor(resolved, tokens, seen);
    return auditVar.fallback ? resolveAuditColor(auditVar.fallback, tokens, seen) : null;
  }

  const parsed = parseColorValue(value);
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

  return parsed.type === "oklch" ? resolveColor(value, tokens) : null;
}

function getTextUsageTier(textName) {
  if (TEXT_USAGE_TIERS[textName]) return TEXT_USAGE_TIERS[textName];
  if (textName === "text-error" || textName === "text-warning" || textName === "text-success") {
    return "data-critical";
  }
  return "operational";
}

function classifyByTier(usageTier, ratio) {
  const gate = USAGE_TIER_GATES[usageTier];

  if (usageTier === "decorative") {
    return { usageTier, status: "report", pass: true, requiresNonColorMarker: gate.requiresNonColorMarker };
  }

  if (usageTier === "metadata" || usageTier === "badge") {
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

function classifyContrast(textName, ratio) {
  return classifyByTier(getTextUsageTier(textName), ratio);
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

function auditDomainFgs(themes, results, counts, unresolved) {
  for (const { name: themeName, tokens } of themes) {
    for (const surfName of DOMAIN_FG_SURFACES) {
      const surfVal = tokens[surfName];
      const surfColor = surfVal ? resolveAuditColor(surfVal, tokens) : null;
      if (!surfColor) {
        addUnresolved(unresolved, surfName, `domain-fg surface (${themeName})`, surfVal ? `could not resolve ${surfVal}` : "missing from token map");
        continue;
      }
      for (const fgName of DOMAIN_FG_PATTERNS) {
        const fgVal = tokens[fgName];
        if (!fgVal) {
          addUnresolved(unresolved, fgName, `domain-fg (${themeName})`, "token is declared for audit but missing from token map");
          continue;
        }
        const fgColor = resolveAuditColor(fgVal, tokens);
        if (!fgColor) {
          addUnresolved(unresolved, fgName, `domain-fg (${themeName})`, `could not resolve ${fgVal}`);
          continue;
        }
        const ratio = contrastRatio(surfColor.luminance, fgColor.luminance);
        const classification = classifyContrast(fgName, ratio);
        updateCounts(classification, counts);
        results.push({
          surface: `${surfName} (${themeName})`,
          text: fgName,
          ratio,
          level: wcagLevel(ratio),
          ...classification,
        });
      }
    }
  }
}

function compositeEffLuminance(bgColor, surfColor) {
  // CSS alpha compositing happens per channel in gamma-encoded sRGB space,
  // then converts to relative luminance for the WCAG ratio.
  const alpha = bgColor.alpha;
  const effR = bgColor.rgb[0] * alpha + surfColor.rgb[0] * (1 - alpha);
  const effG = bgColor.rgb[1] * alpha + surfColor.rgb[1] * (1 - alpha);
  const effB = bgColor.rgb[2] * alpha + surfColor.rgb[2] * (1 - alpha);
  return (
    0.2126 * (effR <= 0.03928 ? effR / 12.92 : ((effR + 0.055) / 1.055) ** 2.4) +
    0.7152 * (effG <= 0.03928 ? effG / 12.92 : ((effG + 0.055) / 1.055) ** 2.4) +
    0.0722 * (effB <= 0.03928 ? effB / 12.92 : ((effB + 0.055) / 1.055) ** 2.4)
  );
}

function auditBadgeCombos(themes, results, counts, unresolved) {
  for (const { name: themeName, tokens } of themes) {
    const surfVal = tokens["surface-panel-base"];
    const surfColor = surfVal ? resolveAuditColor(surfVal, tokens) : null;
    if (!surfColor) {
      addUnresolved(unresolved, "surface-panel-base", `badge base (${themeName})`, "badge composite base is missing or unresolvable");
      continue;
    }
    for (const [fgName, bgName] of BADGE_COMBOS) {
      const fgVal = tokens[fgName];
      const bgVal = tokens[bgName];
      if (!fgVal || !bgVal) {
        addUnresolved(unresolved, `${fgName}/${bgName}`, `badge (${themeName})`, "combo token missing from token map");
        continue;
      }
      const fgColor = resolveAuditColor(fgVal, tokens);
      const bgColor = resolveAuditColor(bgVal, tokens);
      if (!fgColor || !bgColor) {
        addUnresolved(unresolved, `${fgName}/${bgName}`, `badge (${themeName})`, "combo color unresolvable");
        continue;
      }
      const ratio = contrastRatio(compositeEffLuminance(bgColor, surfColor), fgColor.luminance);
      const classification = classifyByTier("badge", ratio);
      updateCounts(classification, counts);
      results.push({
        surface: `${bgName} (on panel-base, ${themeName})`,
        text: fgName,
        ratio,
        level: wcagLevel(ratio),
        composited: true,
        ...classification,
      });
    }
  }
}

// ── Main ──

function auditChartSeries(themes, results, counts, unresolved) {
  for (const { name: themeName, tokens } of themes) {
    const surfVal = tokens[CHART_SURFACE];
    if (!surfVal) {
      addUnresolved(unresolved, CHART_SURFACE, "chart-surface", "token is declared for audit but missing from token map");
      continue;
    }
    const surfColor = resolveAuditColor(surfVal, tokens);
    if (!surfColor) {
      addUnresolved(unresolved, CHART_SURFACE, "chart-surface", `could not resolve ${surfVal}`);
      continue;
    }
    for (const seriesName of CHART_SERIES_PATTERNS) {
      const seriesVal = tokens[seriesName];
      if (!seriesVal) {
        addUnresolved(unresolved, seriesName, `chart-series (${themeName})`, "token is declared for audit but missing from token map");
        continue;
      }
      const seriesColor = resolveAuditColor(seriesVal, tokens);
      if (!seriesColor) {
        addUnresolved(unresolved, seriesName, `chart-series (${themeName})`, `could not resolve ${seriesVal}`);
        continue;
      }
      const ratio = contrastRatio(surfColor.luminance, seriesColor.luminance);
      const level = wcagLevel(ratio);
      const classification = {
        usageTier: "data-critical",
        status: ratio < USAGE_TIER_GATES["data-critical"].failBelow ? "fail" : "pass",
        pass: ratio >= USAGE_TIER_GATES["data-critical"].failBelow,
        requiresNonColorMarker: true,
      };
      updateCounts(classification, counts);
      results.push({
        surface: `${CHART_SURFACE} (${themeName})`,
        text: seriesName,
        ratio,
        level,
        ...classification,
      });
    }
  }
}

function main() {
  const tokens = buildTokenMap("dark");
  const results = [];
  const counts = {
    pass: 0,
    fail: 0,
    warn: 0,
    report: 0,
  };
  const unresolved = [];
  const skipped = [];

  const themes = [
    { name: "dark", tokens },
    { name: "light", tokens: buildTokenMap("light") },
  ];

  // Surface × Text pairs, BOTH themes (#558：text 家族 light 校准获得工具守护)
  for (const { name: themeName, tokens: themeTokens } of themes) {
    for (const surfName of SURFACE_PATTERNS) {
      for (const textName of TEXT_PATTERNS) {
        const surfVal = themeTokens[surfName];
        const textVal = themeTokens[textName];
        if (!surfVal) {
          addUnresolved(unresolved, surfName, `surface (${themeName})`, "token is declared for audit but missing from token map");
          continue;
        }
        if (!textVal) {
          addUnresolved(unresolved, textName, `text (${themeName})`, "token is declared for audit but missing from token map");
          continue;
        }

        const surfColor = resolveAuditColor(surfVal, themeTokens);
        const textColor = resolveAuditColor(textVal, themeTokens);

        if (!surfColor) {
          addUnresolved(unresolved, surfName, `surface (${themeName})`, `could not resolve ${surfVal}`);
          continue;
        }
        if (!textColor) {
          addUnresolved(unresolved, textName, `text (${themeName})`, `could not resolve ${textVal}`);
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
          surface: `${surfName} (${themeName})`,
          text: textName,
          ratio,
          level,
          ...classification,
        });
      }
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

      const effLum = compositeEffLuminance(bgColor, surfColor);

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

  // Chart Cockpit series × chart pane surface, audited in BOTH themes (dark :root + light overlay)
  auditChartSeries(themes, results, counts, unresolved);

  // Domain fg × primary surfaces, BOTH themes (#555)
  auditDomainFgs(themes, results, counts, unresolved);

  // Badge 同色淡底组合（UI 组件级 3:1 裁决档），BOTH themes（#555）
  auditBadgeCombos(themes, results, counts, unresolved);

  // Sort: failures first, then warnings, then reports, then passes
  const statusOrder = { fail: 0, warn: 1, report: 2, pass: 3 };
  results.sort((a, b) => {
    if (a.status !== b.status) return statusOrder[a.status] - statusOrder[b.status];
    return a.ratio - b.ratio;
  });

  // ── Output ──

  console.log("\n## WCAG 2.1 Contrast Audit — Dark Mode (:root defaults) + chart/domain fg/badge in both themes\n");
  console.log(`Pairs checked: ${results.length}`);
  console.log(
    `${emoji(7)} Pass: ${counts.pass}  ${emoji(3)} Warn: ${counts.warn}  ${emoji(1)} Failed pairs: ${counts.fail}  Unresolved: ${unresolved.length}  Report: ${counts.report}\n`,
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
  console.log(
    totalFailures === 0
      ? "All gating pairs pass their contrast tier."
      : `${counts.fail} pair(s) fail contrast tier gates; ${unresolved.length} unresolved audit token(s).`,
  );

  const reportOnly = process.argv.includes("--report-only");
  process.exit(!reportOnly && totalFailures > 0 ? 1 : 0);
}

main();
