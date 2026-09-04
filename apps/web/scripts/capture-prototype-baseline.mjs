#!/usr/bin/env bun

import { createHash } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { basename, join, relative, resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { chromium } from "playwright";
import { activePrototypePages, buildPrototypeBaselineRecord } from "./product-recovery-core.mjs";

const ROOT = resolve(import.meta.dirname, "..");
const PROTOTYPES_DIR = resolve(ROOT, "docs/designs/specs/prototypes");
const CONTRACTS_DIR = resolve(ROOT, "docs/contracts/pages");
const RECORD_PATH = resolve(PROTOTYPES_DIR, ".frozen-baseline.json");
const SCREENSHOT_DIR = resolve(ROOT, "test-results/prototype-baseline/2026-08-29");
const FIXED_NOW = "2026-08-25T09:30:00+08:00";

function sha256(buffer) {
	return createHash("sha256").update(buffer).digest("hex");
}

async function readJson(path) {
	return JSON.parse(await readFile(path, "utf-8"));
}

async function readContracts() {
	const manifest = await readJson(resolve(PROTOTYPES_DIR, ".edition-manifest.json"));
	const contracts = new Map();
	for (const page of activePrototypePages(manifest)) {
		const contract = await readJson(resolve(CONTRACTS_DIR, `${page.id}.contract.json`)).catch(async () => {
			const candidates = ["agent-console.contract.json"];
			for (const candidate of candidates) {
				const value = await readJson(resolve(CONTRACTS_DIR, candidate));
				if (basename(value.prototypeRef) === page.file) return value;
			}
			throw new Error(`Missing page contract for ${page.id}`);
		});
		contracts.set(page.id, contract);
	}
	return { manifest, contracts };
}

async function checkFrozenSources() {
	const record = await readJson(RECORD_PATH);
	const drift = [];
	for (const entry of record.entries) {
		const source = await readFile(resolve(PROTOTYPES_DIR, entry.file));
		if (sha256(source) !== entry.sourceSha256) drift.push(entry.file);
	}
	if (drift.length > 0) {
		throw new Error(`Frozen prototype baseline drifted:\n${drift.map((file) => `  - ${file}`).join("\n")}`);
	}
	console.log(`[prototype-freeze] ${record.entries.length} frozen prototype sources match ${record.baselineCommit}.`);
}

async function capture() {
	const { manifest, contracts } = await readContracts();
	const pages = activePrototypePages(manifest);
	const browser = await chromium.launch({ channel: "chromium" });
	const artifacts = new Map();
	await mkdir(SCREENSHOT_DIR, { recursive: true });

	try {
		for (const prototype of pages) {
			const contract = contracts.get(prototype.id);
			const viewport = contract.viewports?.find((item) => item.role === "primary") ?? { width: 1536, height: 900 };
			const page = await browser.newPage({ viewport: { width: viewport.width, height: viewport.height } });
			try {
				await page.addInitScript((fixedNow) => {
					const NativeDate = Date;
					class FixedDate extends NativeDate {
						constructor(...args) {
							super(args.length === 0 ? fixedNow : args[0]);
						}
						static now() {
							return new NativeDate(fixedNow).getTime();
						}
					}
					globalThis.Date = FixedDate;
				}, FIXED_NOW);
				await page.goto(pathToFileURL(resolve(PROTOTYPES_DIR, prototype.file)).href, {
					waitUntil: "load",
					timeout: 15_000,
				});
				await page.evaluate(async () => {
					document.documentElement.dataset.theme = "dark";
					document.documentElement.dataset.themePreference = "dark";
					document.documentElement.dataset.density = "compact";
					await document.fonts.ready;
				});
				await page.addStyleTag({
					content: "*,*::before,*::after{animation:none!important;transition:none!important;caret-color:transparent!important}",
				});
				const screenshot = await page.screenshot({ fullPage: false });
				const screenshotPath = resolve(SCREENSHOT_DIR, `${prototype.id}.png`);
				await writeFile(screenshotPath, screenshot);
				const source = await readFile(resolve(PROTOTYPES_DIR, prototype.file));
				artifacts.set(prototype.id, {
					viewport: `${viewport.width}x${viewport.height}`,
					sourceSha256: sha256(source),
					screenshotSha256: sha256(screenshot),
					screenshotRef: relative(ROOT, screenshotPath),
				});
			} finally {
				await page.close();
			}
		}

		const baselineCommit = (await Bun.$`git rev-parse HEAD`.cwd(ROOT).text()).trim();
		const record = buildPrototypeBaselineRecord({
			baselineCommit,
			browserVersion: await browser.version(),
			capturedAt: "2026-08-29",
			pages,
			artifacts,
		});
		await writeFile(RECORD_PATH, `${JSON.stringify(record, null, 2)}\n`);
		console.log(`[prototype-freeze] Captured ${pages.length} prototypes in ${relative(ROOT, RECORD_PATH)}.`);
	} finally {
		await browser.close();
	}
}

if (process.argv.includes("--check")) await checkFrozenSources();
else await capture();
