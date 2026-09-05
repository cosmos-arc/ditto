// ─────────────────────────────────────────────
// Ditto Style Dictionary — Custom OKLCH Transform
// Registers a custom transform + transform group that outputs
// oklch(...) CSS values from DTCG token extensions.
// ─────────────────────────────────────────────

import StyleDictionary from "style-dictionary";
import type { TransformedToken, Config, PlatformConfig } from "style-dictionary";
import type { DittoExtensionMeta } from "./types";

// ── Extension Accessor ───────────────────────

/**
 * Safely extract the com.ditto-app extension from a token.
 *
 * Style Dictionary v5 tokens have a `[key: string]: any` indexer,
 * so we cast to access $extensions. The DTCG $extensions shape is
 * guaranteed by our pipeline output.
 */
function getDittoExtension(token: TransformedToken): DittoExtensionMeta | undefined {
  const extensions = token["$extensions"] as
    | Record<string, DittoExtensionMeta>
    | undefined;
  return extensions?.["com.ditto-app"];
}

// ── Transform Registration ───────────────────

/**
 * Register the custom OKLCH value transform and the "ditto" transform group.
 *
 * The transform handles two cases:
 *   1. Standard color tokens → output oklch() from extension metadata
 *   2. Runtime-dynamic tokens → output raw calc() expression from extension
 *
 * Non-color tokens pass through `$value` as-is (handled by subsequent
 * built-in transforms like `color/css`, `size/css`, etc.).
 */
export function registerOklchTransforms(): void {
  StyleDictionary.registerTransform({
    name: "ditto/oklch",
    type: "value",
    transitive: true,
    filter: (token: TransformedToken): boolean => {
      return token.$type === "color" && getDittoExtension(token)?.oklch !== undefined;
    },
    transform: (
      token: TransformedToken,
      _platform: PlatformConfig,
      _config: Config,
    ): string => {
      const ext = getDittoExtension(token);

      // Runtime-dynamic tokens: output the raw CSS calc expression
      if (ext?.runtimeDynamic && ext.rawCss) {
        return ext.rawCss;
      }

      // Standard color tokens: output the oklch() value
      if (ext?.oklch) {
        return ext.oklch;
      }

      // Fallback: return the original $value
      return String(token.$value ?? token.value ?? "");
    },
  });

  StyleDictionary.registerTransformGroup({
    name: "ditto",
    transforms: [
      "attribute/cti",
      "name/cti/kebab",
      "ditto/oklch",    // custom OKLCH transform (before color/css)
      "color/css",
      "size/css",
      "time/seconds",
      "css/fontFamily",
      "css/fontWeight",
      "cubicBezier/css",
    ],
  });
}

// ── Pipeline Runner ──────────────────────────

/**
 * Run the Style Dictionary build pipeline.
 *
 * 1. Registers custom OKLCH transforms
 * 2. Extends the base config from sd.config.ts
 * 3. Builds all platforms (css, scss, json)
 * 4. Logs output file paths
 */
export async function runStyleDictionary(): Promise<void> {
  // Step 1: Register transforms (must happen before constructing SD instance,
  // because the constructor calls init() → extend() which runs transforms)
  registerOklchTransforms();

  // Step 2: Import config from project root
  // Dynamic import — this file lives in scripts/export-tokens/,
  // sd.config.ts is at the project root.
  const configModule = await import("../../sd.config.js");
  const sdConfig = configModule.default;

  // Step 3: Construct Style Dictionary instance.
  // In v5, the constructor calls init() asynchronously.
  // We must await hasInitialized before building.
  const sd = new StyleDictionary({
    ...sdConfig,
    usesDtcg: true,
  });
  await sd.hasInitialized;

  // Step 4: Build all platforms
  await sd.buildAllPlatforms();

  // Step 5: Report output files
  const platforms = sdConfig.platforms as Record<
    string,
    { buildPath?: string; files?: Array<{ destination: string }> }
  >;
  for (const [name, platform] of Object.entries(platforms)) {
    const buildPath = platform.buildPath ?? "";
    const files = platform.files ?? [];
    for (const file of files) {
      console.log(`  [${name}] ${buildPath}${file.destination}`);
    }
  }
}
