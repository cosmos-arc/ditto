#!/usr/bin/env bun
// ─────────────────────────────────────────────
// Ditto Token Dead-Link Audit
// Scans var(--xxx) references and verifies :root definitions exist
// ─────────────────────────────────────────────

import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { resolve, dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__dirname, "..");
const TOKENS_DIR = resolve(ROOT, "src/styles/design-tokens");
const STYLES_DIR = resolve(ROOT, "src/styles");
const PROTOTYPES_DIR = resolve(ROOT, "prototype");

// ── Collect all :root token declarations ──

function collectAllDeclarations() {
  const declarations = new Set();
  const themeInlineDecls = new Set();

  // 1. All design-tokens/*.css files
  const tokenFiles = readdirSync(TOKENS_DIR)
    .filter((f) => f.endsWith(".css"))
    .sort();

  for (const file of tokenFiles) {
    const css = readFileSync(join(TOKENS_DIR, file), "utf-8");
    const re = /(?:^|\n)\s*--([a-zA-Z0-9_-]+)\s*:/g;
    let match;
    while ((match = re.exec(css)) !== null) {
      declarations.add(`--${match[1]}`);
    }
  }

  // 2. globals.css :root block + @theme inline
  const globalsCss = readFileSync(join(STYLES_DIR, "globals.css"), "utf-8");

  const rootRe = /:root\s*\{([^}]*)\}/gs;
  let rootMatch;
  while ((rootMatch = rootRe.exec(globalsCss)) !== null) {
    const declRe = /--([a-zA-Z0-9_-]+)\s*:/g;
    let decl;
    while ((decl = declRe.exec(rootMatch[1])) !== null) {
      declarations.add(`--${decl[1]}`);
    }
  }

  // @theme inline declarations — self-references within @theme inline are valid
  const themeInlineMatch = globalsCss.match(/@theme\s+inline\s*\{([^}]*)\}/s);
  if (themeInlineMatch) {
    const declRe = /--([a-zA-Z0-9_-]+)\s*:/g;
    let decl;
    while ((decl = declRe.exec(themeInlineMatch[1])) !== null) {
      themeInlineDecls.add(`--${decl[1]}`);
    }
  }

  return { declarations, themeInlineDecls, globalsCss, themeInlineMatch };
}

// ── Extract var() references from CSS ──

function extractVarRefs(cssText) {
  const refs = [];
  const re = /var\(\s*--([a-zA-Z0-9_-]+)/g;
  let match;
  while ((match = re.exec(cssText)) !== null) {
    refs.push(`--${match[1]}`);
  }
  return refs;
}

// ── Extract Tailwind arbitrary-value variable shorthands from TS/TSX ──
// Matches `bg-(--token)` / `text-[--token]` shorthands, incl. modifiers:
// opacity `(--token/50)`, fallback `(--token|--fallback)`, data-type
// prefix `(length:--token)`. The `-(`/`-[` prefixes exclude `var(--token)`
// in JS template strings.

function extractShorthandRefs(sourceText) {
  const refs = [];
  const paren = /-\((?:[a-z-]+:)?--([a-zA-Z0-9_-]+)(?:[/|][^)]*)?\)/g;
  const bracket = /-\[(?:[a-z-]+:)?--([a-zA-Z0-9_-]+)(?:[/|][^\]]*)?\]/g;
  for (const re of [paren, bracket]) {
    let match;
    while ((match = re.exec(sourceText)) !== null) {
      refs.push(`--${match[1]}`);
    }
  }
  return refs;
}

function walkSourceFiles(dir, extensions, exclude, files = []) {
  for (const entry of readdirSync(dir)) {
    const path = join(dir, entry);
    if (statSync(path).isDirectory()) {
      walkSourceFiles(path, extensions, exclude, files);
    } else if (extensions.some((ext) => entry.endsWith(ext)) && !exclude.some((ex) => entry.includes(ex))) {
      files.push(path);
    }
  }
  return files;
}

function extractDeclarations(cssText) {
  const declarations = new Set();
  const re = /--([a-zA-Z0-9_-]+)\s*:/g;
  let match;
  while ((match = re.exec(cssText)) !== null) {
    declarations.add(`--${match[1]}`);
  }
  return declarations;
}

function isInsideRoot(path) {
  const pathFromRoot = relative(ROOT, path);
  return pathFromRoot === "" || (!pathFromRoot.startsWith("..") && !pathFromRoot.startsWith("/"));
}

function localStylesheetPaths(html, htmlPath) {
  const paths = [];
  const linkTags = html.match(/<link\b[^>]*>/gi) || [];
  for (const tag of linkTags) {
    if (!/\brel\s*=\s*["']stylesheet["']/i.test(tag)) continue;
    const href = tag.match(/\bhref\s*=\s*["']([^"']+)["']/i)?.[1];
    if (!href || /^(?:[a-z]+:|\/\/|data:)/i.test(href)) continue;
    const path = resolve(dirname(htmlPath), href.split(/[?#]/u, 1)[0]);
    if (isInsideRoot(path) && existsSync(path)) paths.push(path);
  }
  return paths;
}

function readStylesheetGraph(entryPaths) {
  const visited = new Set();
  const chunks = [];

  function visit(path) {
    if (visited.has(path) || !isInsideRoot(path) || !existsSync(path)) return;
    visited.add(path);
    const css = readFileSync(path, "utf-8");
    chunks.push(css);

    const imports = css.matchAll(/@import\s+(?:url\(\s*)?["']([^"']+)["']/gi);
    for (const match of imports) {
      const href = match[1];
      if (!href || /^(?:[a-z]+:|\/\/|data:)/i.test(href)) continue;
      visit(resolve(dirname(path), href.split(/[?#]/u, 1)[0]));
    }
  }

  for (const path of entryPaths) visit(path);
  return chunks.join("\n");
}

// ── Known safe var() patterns (Tailwind internals) ──

const SAFE_REFS = new Set([
  "--tw-shadow",
  "--tw-shadow-color",
  "--tw-ring-offset-shadow",
  "--tw-ring-shadow",
  "--tw-translate-x",
  "--tw-translate-y",
  "--tw-rotate",
  "--tw-skew-x",
  "--tw-skew-y",
  "--tw-scale-x",
  "--tw-scale-y",
  "--tw-gradient-from",
  "--tw-gradient-via",
  "--tw-gradient-to",
  "--tw-gradient-stops",
  "--tw-gradient-position",
]);

// ── Known pre-existing dead shorthand links (#553 cleanup) ──
// #237 审计扩展首次扫描时仓内已存在的未声明 token：值 = 基线出现次数（逐次计数）。
// 门禁语义 = 不允许新增死链，也不允许存量死链的引用次数增长（防同名复发）；
// 当前次数 ≤ 基线只报告不拦截。#553 清偿后删除本表即收紧为全量。

const KNOWN_SHORTHAND_GAPS = new Map([
  ["--color-accent-foreground", 3],
  ["--color-accent-primary", 2],
  ["--color-agent-running-fg", 2],
  ["--color-border-emphasis", 1],
  ["--color-border-warning", 1],
  ["--color-interaction-focus-ring", 1],
  ["--color-led-danger", 65],
  ["--color-led-danger-bg", 1],
  ["--color-led-info", 2],
  ["--color-led-info-bg", 1],
  ["--color-led-success-bg", 4],
  ["--color-led-warning", 19],
  ["--color-led-warning-bg", 6],
  ["--color-model-degrading-fg", 3],
  ["--color-model-drifting-fg", 2],
  ["--color-model-stable-fg", 3],
  ["--color-risk-danger", 2],
  ["--color-risk-high-border", 2],
  ["--color-risk-medium-bg", 1],
  ["--color-risk-medium-fg", 11],
  ["--color-risk-warning-bg", 13],
  ["--color-risk-warning-fg", 53],
  ["--color-status-healthy-bg", 1],
  ["--color-status-healthy-fg", 21],
  ["--color-surface-inset", 1],
  ["--factor-summary-height", 1],
  ["--radius-xs", 1],
  ["--shadow-dragging", 1],
]);

// ── Main ──

function main() {
  const { declarations, themeInlineDecls, globalsCss, themeInlineMatch } = collectAllDeclarations();
  console.log(`\n## Token Dead-Link Audit\n`);
  console.log(`Declared tokens: ${declarations.size}\n`);

  const allResults = [];
  let totalDead = 0;

  // 1. Check design-tokens/*.css
  console.log("### src/styles/design-tokens/\n");
  const tokenCssFiles = readdirSync(TOKENS_DIR)
    .filter((f) => f.endsWith(".css"))
    .sort();

  for (const file of tokenCssFiles) {
    const css = readFileSync(join(TOKENS_DIR, file), "utf-8");
    const refs = extractVarRefs(css);
    const deadLinks = [];
    for (const ref of refs) {
      if (SAFE_REFS.has(ref)) continue;
      if (!declarations.has(ref)) {
        deadLinks.push(ref);
      }
    }
    if (deadLinks.length > 0) {
      const unique = [...new Set(deadLinks)];
      allResults.push({ file: `design-tokens/${file}`, deadLinks: unique });
      totalDead += unique.length;
      console.log(`#### design-tokens/${file}`);
      for (const link of unique) {
        console.log(`  - ${link}`);
      }
      console.log("");
    }
  }

  // 2. Check globals.css :root blocks
  console.log("### src/styles/globals.css (:root block)\n");
  const rootRe = /:root\s*\{([^}]*)\}/gs;
  let rootMatch;
  while ((rootMatch = rootRe.exec(globalsCss)) !== null) {
    const refs = extractVarRefs(rootMatch[1]);
    const deadLinks = [];
    for (const ref of refs) {
      if (SAFE_REFS.has(ref)) continue;
      if (!declarations.has(ref)) {
        deadLinks.push(ref);
      }
    }
    if (deadLinks.length > 0) {
      const unique = [...new Set(deadLinks)];
      allResults.push({ file: "globals.css (:root)", deadLinks: unique });
      totalDead += unique.length;
      for (const link of unique) {
        console.log(`  - ${link}`);
      }
    }
  }

  // 3. Check @theme inline for var() refs that don't resolve to :root
  console.log("### src/styles/globals.css (@theme inline → :root validation)\n");
  if (themeInlineMatch) {
    const themeRefs = extractVarRefs(themeInlineMatch[1]);
    const deadLinks = [];
    for (const ref of themeRefs) {
      if (SAFE_REFS.has(ref)) continue;
      if (themeInlineDecls.has(ref)) continue; // self-reference is valid
      if (!declarations.has(ref)) {
        deadLinks.push(ref);
      }
    }
    if (deadLinks.length > 0) {
      const unique = [...new Set(deadLinks)];
      allResults.push({ file: "globals.css (@theme inline)", deadLinks: unique });
      totalDead += unique.length;
      for (const link of unique) {
        console.log(`  - ${link} (referenced in @theme inline but not in :root)`);
      }
      console.log("");
    } else {
      console.log("All @theme inline var() refs resolve to :root declarations or self-references.\n");
    }
  }

  // 4. Check theme override files
  const themesDir = join(STYLES_DIR, "themes");
  try {
    const themeFiles = readdirSync(themesDir).filter((f) => f.endsWith(".css")).sort();
    console.log("### src/styles/themes/\n");
    for (const file of themeFiles) {
      const css = readFileSync(join(themesDir, file), "utf-8");
      const refs = extractVarRefs(css);
      const deadLinks = [];
      for (const ref of refs) {
        if (SAFE_REFS.has(ref)) continue;
        if (!declarations.has(ref)) {
          deadLinks.push(ref);
        }
      }
      if (deadLinks.length > 0) {
        const unique = [...new Set(deadLinks)];
        allResults.push({ file: `themes/${file}`, deadLinks: unique });
        totalDead += unique.length;
        console.log(`#### themes/${file}`);
        for (const link of unique) {
          console.log(`  - ${link}`);
        }
        console.log("");
      }
    }
  } catch {
    // themes dir may not exist
  }

  // 5. Check prototype HTML files for var() refs in <style> blocks
  console.log("### prototype/\n");
  let protoFilesChecked = 0;
  let protoDeadLinks = 0;
  try {
    const protoFiles = readdirSync(PROTOTYPES_DIR)
      .filter((f) => f.endsWith(".html"))
      .sort();

    for (const file of protoFiles) {
      const htmlPath = join(PROTOTYPES_DIR, file);
      const html = readFileSync(htmlPath, "utf-8");
      const styleBlocks = html.match(/<style[^>]*>([\s\S]*?)<\/style>/gi) || [];
      const inlineStyles = html.match(/style="[^"]*"/gi) || [];
      const linkedCss = readStylesheetGraph(localStylesheetPaths(html, htmlPath));
      const allCss = linkedCss + "\n" + styleBlocks.join("\n") + "\n" + inlineStyles.join("\n");

      if (!allCss.trim()) continue;
      protoFilesChecked++;

      const refs = extractVarRefs(allCss);
      const localDeclarations = extractDeclarations(allCss);
      const fileDeadLinks = new Set();
      for (const ref of refs) {
        if (SAFE_REFS.has(ref)) continue;
        if (localDeclarations.has(ref)) continue;
        if (!declarations.has(ref)) {
          fileDeadLinks.add(ref);
        }
      }
      if (fileDeadLinks.size > 0) {
        protoDeadLinks += fileDeadLinks.size;
        for (const link of fileDeadLinks) {
          console.log(`  - ${file}: ${link}`);
        }
      }
    }
  } catch {
    // prototypes dir may not exist
  }
  totalDead += protoDeadLinks;
  console.log(`Checked ${protoFilesChecked} prototype files, ${protoDeadLinks} dead link(s).\n`);

  // 6. Check Tailwind variable shorthands in src TS/TSX (#237: 弥补 audit 未覆盖
  //    任意值简写用法导致的死链漏报；测试文件排除——注释/示例文本非真实引用。
  //    KNOWN_SHORTHAND_GAPS 钉基线计数：新 token 或存量次数增长都算新死链)
  console.log("### src/ TS/TSX Tailwind variable shorthands\n");
  const sourceFiles = walkSourceFiles(join(ROOT, "src"), [".tsx", ".ts"], [".test.", ".stories."]);
  let shorthandChecked = 0;
  let shorthandDeadLinks = 0;
  const gapOccurrences = new Map(); // token -> current count
  const newViolations = []; // { file, token, reason }
  for (const filePath of sourceFiles) {
    const source = readFileSync(filePath, "utf-8");
    const refs = extractShorthandRefs(source);
    if (refs.length === 0) continue;
    shorthandChecked++;
    for (const ref of refs) {
      if (SAFE_REFS.has(ref) || themeInlineDecls.has(ref) || declarations.has(ref)) continue;
      gapOccurrences.set(ref, (gapOccurrences.get(ref) ?? 0) + 1);
      if (!KNOWN_SHORTHAND_GAPS.has(ref)) {
        newViolations.push({ file: relative(ROOT, filePath), token: ref, reason: "undeclared" });
      }
    }
  }
  for (const [token, baseline] of KNOWN_SHORTHAND_GAPS) {
    const current = gapOccurrences.get(token) ?? 0;
    if (current > baseline) {
      newViolations.push({
        file: "(multiple)",
        token,
        reason: `grew: ${current} > baseline ${baseline}`,
      });
    }
  }
  if (newViolations.length > 0) {
    shorthandDeadLinks += newViolations.length;
    for (const violation of newViolations) {
      console.log(`  - ${violation.file}: ${violation.token} (${violation.reason})`);
    }
  }
  totalDead += shorthandDeadLinks;
  const knownTotal = [...gapOccurrences.entries()].reduce(
    (sum, [token, count]) => sum + (KNOWN_SHORTHAND_GAPS.has(token) ? count : 0),
    0,
  );
  console.log(`Checked ${shorthandChecked} source files, ${shorthandDeadLinks} new dead link(s).`);
  if (knownTotal > 0) {
    console.log(
      `(${knownTotal} occurrences are KNOWN_SHORTHAND_GAPS baseline — pre-existing, see #553; remove the map once cleared.)`,
    );
  }
  console.log("");

  // 7. Summary
  console.log("---\n");
  console.log(`Total dead links: ${totalDead}`);
  if (totalDead === 0) {
    console.log("All var() references resolve to declared tokens.");
  }

  // Exit 0 always — informational audit. Use --ci to gate on failures.
  const isCI = process.argv.includes("--ci");
  process.exit(isCI && totalDead > 0 ? 1 : 0);
}

main();
