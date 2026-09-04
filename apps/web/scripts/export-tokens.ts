// ─────────────────────────────────────────────
// Ditto DTCG Token Export — CLI Entry Point
// Thin CLI layer: parses --check / --schema-only flags,
// delegates to the pipeline orchestrator.
// ─────────────────────────────────────────────

import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { runPipeline, validateDtcgOutput } from "./export-tokens/index.ts";
import type { PipelineResult, ValidationResult } from "./export-tokens/index.ts";

// ── CLI Modes ────────────────────────────────

type CliMode = "default" | "check" | "schema-only";

// ── Argument Parsing ─────────────────────────

function parseArgs(argv: string[]): CliMode {
  const flags = new Set(argv);

  if (flags.has("--help") || flags.has("-h")) {
    printUsage();
    process.exit(0);
  }

  if (flags.has("--check") && flags.has("--schema-only")) {
    console.error("Error: --check and --schema-only are mutually exclusive.");
    printUsage();
    process.exit(1);
  }

  if (flags.has("--check")) return "check";
  if (flags.has("--schema-only")) return "schema-only";
  return "default";
}

function printUsage(): void {
  const lines = [
    "Usage: bun scripts/export-tokens.ts [options]",
    "",
    "Options:",
    "  (none)          Run pipeline and print summary",
    "  --check         Run pipeline, validate output, exit 0/1",
    "  --schema-only   Run pipeline and print schema structure",
    "  --help, -h      Show this help message",
  ];
  for (const line of lines) {
    console.log(line);
  }
}

// ── Main ─────────────────────────────────────

const mode = parseArgs(process.argv.slice(2));

main().catch((error: unknown) => {
  const message = error instanceof Error ? error.message : String(error);
  console.error(`Error: ${message}`);
  process.exit(1);
});

async function main(): Promise<void> {
  const result = await runPipeline();

  printHeader();

  printSummary(result);

  if (mode === "check") {
    const validation = validateDtcgOutput(result.outputDir);
    printValidation(validation);
    if (!validation.valid) {
      process.exit(1);
    }
  }
}

// ── Output Formatting ────────────────────────

function printHeader(): void {
  console.log("Ditto Token Export Pipeline");
  console.log("===========================");
}

function printSummary(result: PipelineResult): void {
  const layerCount = result.tokensByLayer.size;
  console.log(`Parsed ${result.totalTokens} tokens from ${layerCount} layers`);
  console.log("");

  printTokenFiles(result);
  printThemeFiles(result);

  console.log(`Output: ${result.outputDir}`);
}

function printTokenFiles(result: PipelineResult): void {
  console.log("Token files:");
  for (const [layer, count] of result.tokensByLayer) {
    const label = `${layer}.json`.padEnd(22);
    console.log(`  ${label} ${String(count).padStart(3)} tokens`);
  }
  console.log("");
}

function printThemeFiles(result: PipelineResult): void {
  console.log("Theme files:");
  const rootDefaults = new Set(["dark.json"]);

  for (const themeFile of result.themesGenerated) {
    const label = themeFile.padEnd(22);

    if (rootDefaults.has(themeFile)) {
      console.log(`  ${label} (root defaults)`);
    } else {
      const themePath = resolve(result.outputDir, "themes", themeFile);
      const overrides = countOverrides(themePath);
      console.log(`  ${label} ${String(overrides).padStart(3)} overrides`);
    }
  }
  console.log("");
}

function printValidation(validation: ValidationResult): void {
  if (validation.errors.length === 0 && validation.warnings.length === 0) {
    console.log("Validation: passed (no errors, no warnings)");
    return;
  }

  console.log(
    `Validation: ${validation.errors.length} error(s), ${validation.warnings.length} warning(s)`,
  );

  for (const warning of validation.warnings) {
    console.log(`  WARN  ${warning}`);
  }
  for (const error of validation.errors) {
    console.log(`  ERROR ${error}`);
  }
}

// ── Helpers ──────────────────────────────────

/**
 * Count the number of token override entries in a theme JSON file.
 */
function countOverrides(filePath: string): number {
  try {
    const raw = readFileSync(filePath, "utf-8");
    const parsed = JSON.parse(raw) as Record<string, unknown>;
    return countLeafTokens(parsed);
  } catch {
    return 0;
  }
}

/**
 * Recursively count leaf-level DTCG token entries in a nested object.
 * A leaf token is an object that contains a `$value` key.
 */
function countLeafTokens(obj: unknown): number {
  if (obj === null || typeof obj !== "object" || Array.isArray(obj)) return 0;

  let count = 0;
  for (const value of Object.values(obj as Record<string, unknown>)) {
    if (value === null || typeof value !== "object" || Array.isArray(value)) {
      continue;
    }
    const record = value as Record<string, unknown>;
    if ("$value" in record) {
      count++;
    } else {
      count += countLeafTokens(value);
    }
  }
  return count;
}
