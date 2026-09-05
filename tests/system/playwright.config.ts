import { defineConfig } from "@playwright/test";

const outputRoot = process.env["DITTO_SYSTEM_OUTPUT_ROOT"] ?? ".cache/system-e2e";

export default defineConfig({
	testDir: ".",
	fullyParallel: false,
	retries: 0,
	workers: 1,
	timeout: 30_000,
	outputDir: `${outputRoot}/results`,
	reporter: [
		["list"],
		["html", { outputFolder: `${outputRoot}/report`, open: "never" }],
	],
	use: {
		baseURL: process.env["DITTO_SYSTEM_WEB_ORIGIN"],
		trace: "retain-on-failure",
		screenshot: "only-on-failure",
		video: "retain-on-failure",
	},
	projects: [{ name: "chromium", use: { browserName: "chromium" } }],
});
