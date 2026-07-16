#!/usr/bin/env bun
/**
 * Contract Create — 从 prototype 探测 DOM 结构、提取度量
 *
 * 这是 --create 命令的自动化部分（Phase P/S/M）。
 * Phase R（Resolve）和 Phase B（Blueprint Extract）由 AI skill 执行。
 * Phase W（Write）由 AI skill 组装最终 JSON。
 *
 * Usage:
 *   bun .claude/skills/ditto-page-contract/scripts/create.mjs --prototype docs/designs/specs/prototypes/page-home.html
 */

import { chromium } from "playwright";
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { resolve, dirname } from "node:path";

const PROTOTYPE_NORMALIZE_CSS = `
  .proto-nav { display: none !important; }
  #default-view {
    height: 100vh !important;
    min-height: 100vh !important;
    overflow: hidden !important;
  }
  #default-view > [class*="shell"],
  #default-view > .ai-shell,
  #default-view > .intel-shell,
  #default-view > .risk-shell {
    height: 100vh !important;
    min-height: 0 !important;
    flex: 0 0 auto !important;
  }
  #default-view > .status-bar {
    height: 24px !important;
    flex: 0 0 auto !important;
  }
`;

/**
 * Phase P: PROTOTYPE PROBE — 探测 prototype DOM 结构
 */
async function probePrototype(page) {
  return page.evaluate(() => {
    const view = document.getElementById("default-view");
    if (!view) return { error: "#default-view not found" };

    // Walk the DOM tree to build a structural summary
    const summary = [];
    function walk(el, depth = 0) {
      if (depth > 4) return; // Limit depth
      const tag = el.tagName.toLowerCase();
      if (tag === "script" || tag === "style" || tag === "link") return;

      const cls = el.className
        ? typeof el.className === "string"
          ? el.className.split(/\s+/).filter(Boolean)
          : []
        : [];
      const dataAttrs = {};
      for (const attr of el.attributes) {
        if (attr.name.startsWith("data-")) {
          dataAttrs[attr.name] = attr.value;
        }
      }

      // Only record elements with meaningful classes or data attributes
      if (cls.length > 0 || Object.keys(dataAttrs).length > 0) {
        const entry = {
          tag,
          classes: cls.slice(0, 5),
          dataAttrs,
          childCount: el.children.length,
        };
        summary.push(entry);
      }

      for (const child of el.children) {
        walk(child, depth + 1);
      }
    }

    walk(view);

    // Extract named sections: two-pass strategy
    const sections = [];

    // Pass 1: data-contract-slot attributes (deterministic, preferred)
    const slotElements = view.querySelectorAll("[data-contract-slot]");
    for (const el of slotElements) {
      const slotName = el.getAttribute("data-contract-slot");
      sections.push({
        name: slotName,
        selector: `[data-contract-slot="${slotName}"]`,
        found: true,
        method: "data-contract-slot",
      });
    }

    // Pass 2: Fallback — class-name probing (only for sections not found in Pass 1)
    const foundNames = new Set(sections.map((s) => s.name));
    const fallbackSelectors = [
      { name: "pulse", selector: ".shell-pulse" },
      { name: "main", selector: ".shell-main" },
      { name: "sidebar", selector: ".shell-sidebar" },
      { name: "rail", selector: ".shell-rail" },
      { name: "header", selector: ".shell-header" },
      { name: "decision-banner", selector: ".decision-banner" },
      { name: "priority-queue", selector: ".panel-grow" },
      { name: "secondary", selector: ".shell-secondary" },
      { name: "status-bar", selector: ".status-bar" },
      { name: "scope-strip", selector: ".scope-strip" },
      { name: "context-bar", selector: ".context-bar" },
      { name: "right-rail", selector: ".right-rail" },
      { name: "tab-band", selector: ".tab-band" },
      { name: "activity", selector: ".shell-activity" },
      { name: "analysis", selector: ".shell-analysis" },
      { name: "detail", selector: ".shell-detail" },
      { name: "meta", selector: ".hub-meta" },
      { name: "tabs", selector: ".hub-tabs" },
      { name: "bottom", selector: ".hub-bottom" },
      { name: "source", selector: ".studio-sources" },
      { name: "inspector", selector: ".studio-inspector" },
      { name: "toolbar", selector: ".catalog-toolbar, .screener-toolbar" },
    ];
    for (const { name, selector } of fallbackSelectors) {
      if (foundNames.has(name)) continue;
      const el = view.querySelector(selector);
      if (el) {
        sections.push({ name, selector, found: true, method: "class-fallback" });
      }
    }

    return { totalElements: summary.length, sections };
  });
}

/**
 * Phase M: METRIC CAPTURE — 提取布局度量
 */
async function captureMetrics(page, viewport) {
  return page.evaluate((vp) => {
    const results = {};

    const targets = [
      { name: "pulse", selector: "[data-contract-slot='pulse'], .shell-pulse" },
      { name: "main", selector: "[data-contract-slot='main'], .shell-main" },
      { name: "sidebar", selector: "[data-contract-slot='sidebar'], .shell-sidebar" },
      { name: "rail", selector: "[data-contract-slot='rail'], .shell-rail" },
      { name: "header", selector: "[data-contract-slot='header'], .shell-header" },
      { name: "decision-banner", selector: "[data-contract-slot='decision-banner'], .decision-banner" },
      { name: "priority-queue", selector: "[data-contract-slot='priority-queue'], .panel-grow" },
      { name: "secondary", selector: "[data-contract-slot='secondary'], .shell-secondary" },
      { name: "status-bar", selector: "[data-contract-slot='status-bar'], .status-bar" },
      { name: "scope-strip", selector: "[data-contract-slot='scope-strip'], .scope-strip" },
      { name: "context-bar", selector: "[data-contract-slot='context-bar'], .context-bar" },
      { name: "right-rail", selector: "[data-contract-slot='right-rail'], .right-rail" },
      { name: "tab-band", selector: "[data-contract-slot='tab-band'], .tab-band" },
    ];

    for (const target of targets) {
      const el = document.querySelector(target.selector);
      if (!el) continue;

      const rect = el.getBoundingClientRect();
      const cs = getComputedStyle(el);

      // Derive layout strategy
      let strategy = "content-driven";
      if (cs.width === `${rect.width}px` && rect.height > 0) {
        const heightRatio = rect.height / vp.height;
        if (heightRatio > 0.8 && heightRatio < 1.2) {
          strategy = "fixed-width";
        }
      }
      if (cs.flex && cs.flex !== "0 0 auto") {
        strategy = "flex";
      }

      results[target.name] = {
        width: Math.round(rect.width),
        height: Math.round(rect.height),
        strategy,
      };
    }

    return results;
  }, viewport);
}

/* ------------------------------------------------------------------ */
/*  Main                                                               */
/* ------------------------------------------------------------------ */

async function main() {
  const args = process.argv.slice(2);
  const prototypeIdx = args.indexOf("--prototype");
  if (prototypeIdx === -1 || !args[prototypeIdx + 1]) {
    console.error("Usage: bun scripts/contract-generator/create.mjs --prototype <path-to-html>");
    process.exit(1);
  }

  const prototypePath = resolve(process.cwd(), args[prototypeIdx + 1]);
  console.log("[create] Prototype:", prototypePath);

  // Read prototype HTML
  const html = await readFile(prototypePath, "utf-8");
  console.log("[create] HTML size:", html.length, "bytes");

  // Launch Playwright
  const browser = await chromium.launch({ channel: "chromium" });
  const viewport = { width: 1536, height: 900 };

  try {
    const page = await browser.newPage({ viewport });

    // Set content directly
    await page.setContent(html, { waitUntil: "networkidle" });

    // Inject normalize CSS
    await page.addStyleTag({ content: PROTOTYPE_NORMALIZE_CSS });

    // Phase P: Probe DOM
    console.log("[create] Phase P: Probing DOM structure...");
    const probe = await probePrototype(page);
    console.log(`[create] Found ${probe.sections.length} named sections`);
    for (const s of probe.sections) {
      console.log(`  - ${s.selector}`);
    }

    // Phase M: Capture metrics
    console.log("[create] Phase M: Capturing metrics...");
    const metrics = await captureMetrics(page, viewport);
    console.log("[create] Metrics baseline:");
    for (const [name, m] of Object.entries(metrics)) {
      console.log(`  ${name}: ${m.width}x${m.height} (${m.strategy})`);
    }

    // Output result
    const result = {
      probe,
      metrics: {
        capturedAt: new Date().toISOString().split("T")[0],
        viewport: `${viewport.width}x${viewport.height}`,
        baseline: metrics,
      },
    };

    // Write to stdout as JSON
    console.log("\n--- JSON OUTPUT ---");
    console.log(JSON.stringify(result, null, 2));
  } finally {
    await browser.close();
  }
}

main().catch((err) => {
  console.error("[create] Fatal:", err);
  process.exit(1);
});
