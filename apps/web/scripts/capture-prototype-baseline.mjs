#!/usr/bin/env bun

import { createHash } from "node:crypto";
import { mkdir, readFile, readdir, writeFile } from "node:fs/promises";
import { basename, join, relative, resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { chromium } from "playwright";
import {
	activePrototypePages,
	buildPrototypeBaselineRecord,
	buildPrototypeSourceEvidence,
} from "./product-recovery-core.mjs";

const ROOT = resolve(import.meta.dirname, "..");
const PROTOTYPES_DIR = resolve(ROOT, "prototype");
const CONTRACTS_DIR = resolve(ROOT, "contracts/pages");
const RECORD_PATH = resolve(PROTOTYPES_DIR, ".frozen-baseline.json");
const FIXED_NOW = "2026-08-25T09:30:00+08:00";

function sha256(buffer) {
	return createHash("sha256").update(buffer).digest("hex");
}

async function readJson(path) {
	return JSON.parse(await readFile(path, "utf-8"));
}

function isInsideWorkspace(path) {
	const workspacePath = relative(ROOT, path);
	return workspacePath === "" || (!workspacePath.startsWith("..") && !workspacePath.startsWith("/"));
}

function localPath(fromPath, reference) {
	const normalized = reference.trim().split(/[?#]/u, 1)[0];
	if (!normalized || /^(?:[a-z][a-z0-9+.-]*:|\/\/|data:)/iu.test(normalized)) return undefined;
	const path = resolve(join(fromPath, ".."), normalized);
	if (!isInsideWorkspace(path)) {
		throw new Error(`Prototype source escapes the Web workspace: ${reference}`);
	}
	if (relative(ROOT, path).split("/").includes("node_modules")) return undefined;
	return path;
}

function referencedFiles(path, content) {
	const references = [];
	if (path.endsWith(".html")) {
		for (const match of content.matchAll(/<link\b[^>]*\bhref\s*=\s*["']([^"']+)["'][^>]*>/giu)) {
			if (/\brel\s*=\s*["']stylesheet["']/iu.test(match[0])) references.push(match[1]);
		}
		for (const match of content.matchAll(/<script\b[^>]*\bsrc\s*=\s*["']([^"']+)["'][^>]*>/giu)) {
			references.push(match[1]);
		}
	} else if (path.endsWith(".css")) {
		for (const match of content.matchAll(/@import\s+(?:url\(\s*)?["']([^"']+)["']/giu)) {
			references.push(match[1]);
		}
		for (const match of content.matchAll(/url\(\s*["']?([^"')]+)["']?\s*\)/giu)) {
			references.push(match[1]);
		}
	} else if (path.endsWith(".js") || path.endsWith(".mjs")) {
		for (const match of content.matchAll(/(?:from\s*|import\s*\(\s*)["']([^"']+)["']/giu)) {
			references.push(match[1]);
		}
	}
	return references.filter((reference) => typeof reference === "string");
}

async function collectPrototypeSourceEvidence(htmlPath) {
	const pending = [htmlPath];
	const visited = new Set();
	const inputs = [];

	while (pending.length > 0) {
		const path = pending.pop();
		if (path === undefined || visited.has(path)) continue;
		visited.add(path);
		let content;
		try {
			content = await readFile(path);
		} catch (error) {
			throw new Error(`Missing local prototype source ${relative(ROOT, path)}`, { cause: error });
		}
		inputs.push({ path: relative(ROOT, path), content });
		const text = content.toString("utf-8");
		for (const reference of referencedFiles(path, text)) {
			const dependencyPath = localPath(path, reference);
			if (dependencyPath !== undefined) pending.push(dependencyPath);
		}
	}

	return buildPrototypeSourceEvidence(inputs);
}

function baselineDate() {
	const value = process.env.DITTO_PROTOTYPE_BASELINE_DATE ?? new Date().toISOString().slice(0, 10);
	if (!/^\d{4}-\d{2}-\d{2}$/u.test(value)) {
		throw new Error(`DITTO_PROTOTYPE_BASELINE_DATE must be YYYY-MM-DD, got ${value}`);
	}
	return value;
}

function assertCommittedSources(paths) {
	const result = Bun.spawnSync(
		["git", "status", "--porcelain=v1", "--untracked-files=all", "--", ...paths],
		{ cwd: ROOT, stdout: "pipe", stderr: "pipe" },
	);
	if (result.exitCode !== 0) throw new Error(result.stderr.toString().trim());
	const dirty = result.stdout.toString().trim();
	if (dirty) {
		throw new Error(
			`Refusing to attribute uncommitted prototype sources to HEAD:\n${dirty}`,
		);
	}
}

async function readContracts() {
	const manifest = await readJson(resolve(PROTOTYPES_DIR, ".edition-manifest.json"));
	const contractFiles = (await readdir(CONTRACTS_DIR))
		.filter((file) => file.endsWith(".contract.json"))
		.sort();
	const contractsByFile = new Map();
	const contractsByPrototype = new Map();
	for (const file of contractFiles) {
		const contract = await readJson(resolve(CONTRACTS_DIR, file));
		contractsByFile.set(file, contract);
		const prototypeFile = basename(contract.prototypeRef ?? "");
		if (!prototypeFile) continue;
		const candidates = contractsByPrototype.get(prototypeFile) ?? [];
		candidates.push(contract);
		contractsByPrototype.set(prototypeFile, candidates);
	}
	const contracts = new Map();
	for (const page of activePrototypePages(manifest)) {
		const direct = contractsByFile.get(`${page.id}.contract.json`);
		const candidates = contractsByPrototype.get(page.file) ?? [];
		const contract = direct ?? candidates[0] ?? { viewports: [] };
		const primaryViewports = new Set(
			candidates.map((candidate) => {
				const viewport = candidate.viewports?.find((item) => item.role === "primary");
				return viewport === undefined ? "1536x900" : `${viewport.width}x${viewport.height}`;
			}),
		);
		if (primaryViewports.size > 1) {
			throw new Error(`Conflicting primary viewports for ${page.file}: ${[...primaryViewports].join(", ")}`);
		}
		contracts.set(page.id, contract);
	}
	return { manifest, contracts };
}

async function checkFrozenSources() {
	const record = await readJson(RECORD_PATH);
	if (record.version !== 2) throw new Error(`Unsupported frozen baseline version: ${record.version}`);
	const drift = [];
	for (const entry of record.entries) {
		const inputs = [];
		for (const input of entry.sourceInputs ?? []) {
			const path = resolve(ROOT, input.path);
			if (!isInsideWorkspace(path)) throw new Error(`Frozen source escapes Web workspace: ${input.path}`);
			const content = await readFile(path).catch(() => undefined);
			if (content === undefined || sha256(content) !== input.sha256) {
				drift.push(`${entry.file}: ${input.path}`);
				continue;
			}
			inputs.push({ path: input.path, content });
		}
		if (inputs.length !== (entry.sourceInputs?.length ?? 0)) continue;
		const evidence = buildPrototypeSourceEvidence(inputs);
		if (evidence.sourceSha256 !== entry.sourceSha256) drift.push(`${entry.file}: aggregate`);
	}
	if (drift.length > 0) {
		throw new Error(`Frozen prototype baseline drifted:\n${drift.map((file) => `  - ${file}`).join("\n")}`);
	}
	console.log(`[prototype-freeze] ${record.entries.length} frozen prototype sources match ${record.baselineCommit}.`);
}

async function capture() {
	const { manifest, contracts } = await readContracts();
	const pages = activePrototypePages(manifest);
	const capturedAt = baselineDate();
	const screenshotDir = resolve(ROOT, "test-results/prototype-baseline", capturedAt);
	const sourceEvidence = new Map();
	for (const prototype of pages) {
		sourceEvidence.set(
			prototype.id,
			await collectPrototypeSourceEvidence(resolve(PROTOTYPES_DIR, prototype.file)),
		);
	}
	assertCommittedSources([
		...new Set(
			[...sourceEvidence.values()].flatMap((evidence) =>
				evidence.sourceInputs.map((input) => input.path),
			),
		),
	]);
	const browser = await chromium.launch({ channel: "chromium" });
	const artifacts = new Map();
	await mkdir(screenshotDir, { recursive: true });

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
				const screenshotPath = resolve(screenshotDir, `${prototype.id}.png`);
				await writeFile(screenshotPath, screenshot);
				const evidence = sourceEvidence.get(prototype.id);
				if (evidence === undefined) throw new Error(`Missing source evidence for ${prototype.id}`);
				artifacts.set(prototype.id, {
					viewport: `${viewport.width}x${viewport.height}`,
					...evidence,
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
			capturedAt,
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
