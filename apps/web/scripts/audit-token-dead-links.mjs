#!/usr/bin/env bun
// ─────────────────────────────────────────────
// Ditto Token Dead-Link Audit
// Scans var(--xxx) references and verifies :root definitions exist
// ─────────────────────────────────────────────

import { readFileSync, readdirSync } from "node:fs";
import { resolve, dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__dirname, "..");
const TOKENS_DIR = resolve(ROOT, "src/styles/design-tokens");
const STYLES_DIR = resolve(ROOT, "src/styles");
const PROTOTYPES_DIR = resolve(ROOT, "docs/designs/specs/prototypes");

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
  console.log("### docs/designs/specs/prototypes/\n");
  let protoFilesChecked = 0;
  let protoDeadLinks = 0;
  try {
    const protoFiles = readdirSync(PROTOTYPES_DIR)
      .filter((f) => f.endsWith(".html"))
      .sort();

    for (const file of protoFiles) {
      const html = readFileSync(join(PROTOTYPES_DIR, file), "utf-8");
      const styleBlocks = html.match(/<style[^>]*>([\s\S]*?)<\/style>/gi) || [];
      const inlineStyles = html.match(/style="[^"]*"/gi) || [];
      const allCss = styleBlocks.join("\n") + "\n" + inlineStyles.join("\n");

      if (!allCss.trim()) continue;
      protoFilesChecked++;

      const refs = extractVarRefs(allCss);
      const fileDeadLinks = new Set();
      for (const ref of refs) {
        if (SAFE_REFS.has(ref)) continue;
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

  // 6. Summary
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
