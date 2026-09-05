// ─────────────────────────────────────────────
// Ditto Style Dictionary Configuration
//
// Platform definitions for building design tokens
// from DTCG JSON source files.
//
// This file does NOT register custom transforms.
// Use runStyleDictionary() from scripts/export-tokens/sd-oklch-transform.ts
// for programmatic usage (it registers transforms before building).
//
// CLI usage:
//   npx style-dictionary build --config sd.config.ts
//   (requires registering transforms separately first)
// ─────────────────────────────────────────────

import type { Config } from "style-dictionary";

const sdConfig: Config = {
	source: ["dist/tokens/tokens/*.json"],
	platforms: {
		css: {
			transformGroup: "ditto",
			buildPath: "dist/sd/css/",
			files: [
				{
					destination: "variables.css",
					format: "css/variables",
					options: { outputReferences: true },
				},
			],
		},
		scss: {
			transformGroup: "ditto",
			buildPath: "dist/sd/scss/",
			files: [
				{
					destination: "_variables.scss",
					format: "scss/variables",
					options: { outputReferences: true },
				},
			],
		},
		json: {
			transformGroup: "ditto",
			buildPath: "dist/sd/json/",
			files: [
				{
					destination: "tokens.json",
					format: "json",
				},
			],
		},
	},
};

export default sdConfig;
