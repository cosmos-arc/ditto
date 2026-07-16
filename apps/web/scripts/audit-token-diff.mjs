#!/usr/bin/env bun
// ─────────────────────────────────────────────
// Ditto Token Version Diff
// Generates a summary report of token changes between git refs
// ─────────────────────────────────────────────

import { execSync } from "node:child_process";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__dirname, "..");
const TOKENS_GLOB = "src/styles/design-tokens/tokens-*.css";

// ── Parse CLI args ──

const args = process.argv.slice(2);
const baseRef = args[0] || "main";
const headRef = args[1] || "HEAD";

// ── Extract token changes from git diff ──

function getTokenDiff(base, head) {
  const diffCmd = `git diff ${base}...${head} -- "${TOKENS_GLOB}"`;
  let diffOutput;
  try {
    diffOutput = execSync(diffCmd, { cwd: ROOT, encoding: "utf-8", maxBuffer: 10 * 1024 * 1024 });
  } catch {
    console.error(`Error: git diff ${base}...${head} failed. Ensure both refs exist.`);
    process.exit(1);
  }

  if (!diffOutput.trim()) {
    return { added: [], modified: [], removed: [], files: [] };
  }

  // Collect changed files
  const files = [];
  const fileRe = /^diff --git a\/(.+?) b\/(.+?)$/gm;
  let fMatch;
  while ((fMatch = fileRe.exec(diffOutput)) !== null) {
    files.push(fMatch[2]);
  }

  // Parse unified diff hunks
  const changes = { added: [], modified: [], removed: [] };

  // Token declaration regex: --name: value;
  const tokenDeclRe = /^([-+ ])--([a-zA-Z0-9_-]+)\s*:\s*([^;}\n]+)/gm;

  // Process hunks — track which tokens were added/removed in each file
  const hunks = diffOutput.split(/^@@/m).slice(1);
  const currentFile = { name: "", additions: new Map(), deletions: new Map() };

  for (const line of diffOutput.split("\n")) {
    // Track current file
    if (line.startsWith("diff --git")) {
      // Push previous file's changes
      if (currentFile.name) {
        mergeChanges(currentFile, changes);
      }
      const parts = line.match(/^diff --git a\/(.+?) b\/(.+?)$/);
      currentFile.name = parts ? parts[2] : "";
      currentFile.additions = new Map();
      currentFile.deletions = new Map();
      continue;
    }

    // Skip metadata lines
    if (line.startsWith("index ") || line.startsWith("--- ") || line.startsWith("+++ ") || line.startsWith("Binary")) {
      continue;
    }

    // Skip context lines
    if (line.startsWith(" ") || line.startsWith("@")) continue;

    // Check for token declarations
    const isAddition = line.startsWith("+");
    const isDeletion = line.startsWith("-");
    if (!isAddition && !isDeletion) continue;

    const content = line.slice(1);
    const tokenMatch = content.match(/^--([a-zA-Z0-9_-]+)\s*:\s*([^;}\n]+)/);
    if (!tokenMatch) continue;

    const tokenName = tokenMatch[1];
    const tokenValue = tokenMatch[2].trim();

    if (isAddition) {
      currentFile.additions.set(tokenName, tokenValue);
    } else {
      currentFile.deletions.set(tokenName, tokenValue);
    }
  }

  // Push last file
  if (currentFile.name) {
    mergeChanges(currentFile, changes);
  }

  return { ...changes, files };
}

function mergeChanges(fileState, changes) {
  for (const [name, value] of fileState.additions) {
    if (fileState.deletions.has(name)) {
      const oldValue = fileState.deletions.get(name);
      if (oldValue !== value) {
        changes.modified.push({
          name: `--${name}`,
          file: fileState.name,
          oldValue,
          newValue: value,
        });
      }
    } else {
      changes.added.push({
        name: `--${name}`,
        file: fileState.name,
        value,
      });
    }
  }

  for (const [name, value] of fileState.deletions) {
    if (!fileState.additions.has(name)) {
      changes.removed.push({
        name: `--${name}`,
        file: fileState.name,
        value,
      });
    }
  }
}

// ── Color value classification ──

function classifyToken(name, value) {
  if (value.includes("oklch")) return "color";
  if (value.includes("rem") || value.includes("px")) return "dimension";
  if (value.includes("ms")) return "duration";
  if (value.includes("cubic-bezier")) return "easing";
  if (value.includes("var(")) return "reference";
  return "other";
}

// ── Main ──

function main() {
  const branchName = execSync("git branch --show-current", { cwd: ROOT, encoding: "utf-8" }).trim();

  console.log(`\n## Token Changes (${baseRef} → ${headRef})\n`);
  console.log(`Branch: ${branchName}\n`);

  const diff = getTokenDiff(baseRef, headRef);

  if (diff.files.length === 0) {
    console.log("No token file changes detected.");
    return;
  }

  console.log(`Files changed: ${diff.files.map((f) => f.replace("src/styles/design-tokens/", "")).join(", ")}\n`);

  // Added
  if (diff.added.length > 0) {
    console.log("### Added\n");
    console.log("| Token | File | Value | Type |");
    console.log("|-------|------|-------|------|");
    for (const t of diff.added.sort((a, b) => a.name.localeCompare(b.name))) {
      console.log(`| ${t.name} | ${t.file.replace("src/styles/design-tokens/", "")} | \`${t.value}\` | ${classifyToken(t.name, t.value)} |`);
    }
    console.log("");
  }

  // Modified
  if (diff.modified.length > 0) {
    console.log("### Modified\n");
    console.log("| Token | File | Old | New | Type |");
    console.log("|-------|------|-----|-----|------|");
    for (const t of diff.modified.sort((a, b) => a.name.localeCompare(b.name))) {
      console.log(
        `| ${t.name} | ${t.file.replace("src/styles/design-tokens/", "")} | \`${t.oldValue}\` | \`${t.newValue}\` | ${classifyToken(t.name, t.newValue)} |`
      );
    }
    console.log("");
  }

  // Removed
  if (diff.removed.length > 0) {
    console.log("### Removed\n");
    console.log("| Token | File | Value | Type |");
    console.log("|-------|------|-------|------|");
    for (const t of diff.removed.sort((a, b) => a.name.localeCompare(b.name))) {
      console.log(`| ${t.name} | ${t.file.replace("src/styles/design-tokens/", "")} | \`${t.value}\` | ${classifyToken(t.name, t.value)} |`);
    }
    console.log("");
  }

  // Summary
  const colorChanges = [
    ...diff.added.filter((t) => classifyToken(t.name, t.value) === "color"),
    ...diff.modified.filter((t) => classifyToken(t.name, t.newValue) === "color"),
  ];

  if (colorChanges.length > 0) {
    console.log("---\n");
    console.log(`Total: +${diff.added.length} ~${diff.modified.length} -${diff.removed.length} (${colorChanges.length} color tokens changed)`);
    console.log("Consider running WCAG contrast audit after color token changes.");
  } else {
    console.log(`Total: +${diff.added.length} ~${diff.modified.length} -${diff.removed.length}`);
  }
}

main();
