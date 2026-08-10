#!/usr/bin/env bun

import { existsSync } from "node:fs";
import { readdir, readFile } from "node:fs/promises";
import path from "node:path";

import { compareTrees } from "./sync-skills.mjs";

const EXPECTED_SKILLS = new Set([
	"ditto-app-dev",
	"ditto-design-cycle",
	"ditto-page-contract",
	"ditto-product-arch",
	"ditto-product-discovery",
]);
const LEGACY_PATHS = [
	[".agents/skills/", ["im", "peccable"].join("")].join(""),
	".agents/skills/source-command-ditto-app-architecture-audit",
	".claude/checklists",
	".claude/commands",
	".claude/hooks",
	".claude/rules",
	"docs/superpowers",
	"skills-lock.json",
];
const REQUIRED_EVENTS = new Set(["PreToolUse", "PostToolUse", "Stop"]);
const REQUIRED_SCRIPTS = new Set([
	"arch:check",
	"check",
	"check:changed",
	"ci",
	"harness:check",
	"harness:sync",
	"harness:validate",
	"routes:generate",
	"test:prototype",
	"test:unit",
]);

function lineCount(text) {
	return text.split(/\r?\n/u).filter((_, index, lines) => index < lines.length - 1 || lines[index] !== "").length;
}

export function parseFrontmatter(text) {
	const lines = text.split(/\r?\n/u);
	if (lines[0] !== "---") throw new Error("missing opening frontmatter delimiter");
	const end = lines.indexOf("---", 1);
	if (end < 0) throw new Error("missing closing frontmatter delimiter");
	const values = {};
	for (const line of lines.slice(1, end)) {
		if (!line.trim()) continue;
		const separator = line.indexOf(":");
		if (separator < 0) throw new Error(`invalid frontmatter line: ${line}`);
		const key = line.slice(0, separator).trim();
		const value = line
			.slice(separator + 1)
			.trim()
			.replace(/^(['"])(.*)\1$/u, "$2");
		if (!key || !value || [">", "|"].includes(value)) throw new Error(`frontmatter must use scalar values: ${line}`);
		values[key] = value;
	}
	if (Object.keys(values).sort().join(",") !== "description,name") {
		throw new Error("frontmatter must contain only name and description");
	}
	return values;
}

async function directoryNames(directory) {
	try {
		return (await readdir(directory, { withFileTypes: true }))
			.filter((entry) => entry.isDirectory())
			.map((entry) => entry.name);
	} catch (error) {
		if (error?.code === "ENOENT") return [];
		throw error;
	}
}

function sameSet(left, right) {
	return left.size === right.size && [...left].every((value) => right.has(value));
}

function eventMatchers(config, event) {
	const entries = config?.hooks?.[event];
	if (!Array.isArray(entries)) return [];
	return entries.map((entry) => entry?.matcher).filter((matcher) => typeof matcher === "string");
}

async function readJson(file, errors, root) {
	try {
		return JSON.parse(await readFile(file, "utf8"));
	} catch (error) {
		errors.push(`invalid or missing JSON ${path.relative(root, file)}: ${error.message}`);
		return null;
	}
}

async function validateInstructions(root, errors) {
	const agents = await readFile(path.join(root, "AGENTS.md"), "utf8");
	const claude = await readFile(path.join(root, "CLAUDE.md"), "utf8");
	if (lineCount(agents) > 150) errors.push("AGENTS.md exceeds 150 lines");
	if (claude.trim() !== "@AGENTS.md" || lineCount(claude) > 3)
		errors.push("CLAUDE.md must be a thin @AGENTS.md wrapper");
}

async function validateSkills(root, errors) {
	const source = path.join(root, ".agents/skills");
	const names = new Set(await directoryNames(source));
	if (!sameSet(names, EXPECTED_SKILLS)) {
		errors.push(`expected skills ${[...EXPECTED_SKILLS].sort().join(", ")}; found ${[...names].sort().join(", ")}`);
	}
	for (const name of [...names].sort()) {
		const skillFile = path.join(source, name, "SKILL.md");
		const metadataFile = path.join(source, name, "agents/openai.yaml");
		try {
			const skill = await readFile(skillFile, "utf8");
			const frontmatter = parseFrontmatter(skill);
			if (frontmatter.name !== name) errors.push(`${name}: frontmatter name does not match directory`);
			if (lineCount(skill) > 120) errors.push(`${name}: SKILL.md exceeds 120 lines`);
			const metadata = await readFile(metadataFile, "utf8");
			if (!metadata.includes(`$${name}`)) errors.push(`${name}: openai.yaml default prompt must mention $${name}`);
		} catch (error) {
			errors.push(`${name}: ${error.message}`);
		}
	}
	errors.push(...(await compareTrees(path.join(root, ".agents/skills"), path.join(root, ".claude/skills"))));
}

async function validateConfigs(root, errors) {
	const settings = await readJson(path.join(root, ".claude/settings.json"), errors, root);
	const codex = await readJson(path.join(root, ".codex/hooks.json"), errors, root);
	const packageJson = await readJson(path.join(root, "package.json"), errors, root);
	if (settings) {
		const enabledPlugins = Object.entries(settings.enabledPlugins ?? {}).filter(([, enabled]) => enabled);
		if (enabledPlugins.length > 0)
			errors.push(`Claude project plugins must be empty; found ${enabledPlugins.map(([name]) => name).join(", ")}`);
		if (settings.permissions?.defaultMode !== "default") errors.push("Claude permissions.defaultMode must be default");
		if (!sameSet(new Set(Object.keys(settings.hooks ?? {})), REQUIRED_EVENTS))
			errors.push("Claude must define PreToolUse, PostToolUse, and Stop hooks");
	}
	if (codex) {
		if (!sameSet(new Set(Object.keys(codex.hooks ?? {})), REQUIRED_EVENTS))
			errors.push("Codex must define PreToolUse, PostToolUse, and Stop hooks");
		if (!eventMatchers(codex, "PostToolUse").some((matcher) => matcher.split("|").includes("apply_patch"))) {
			errors.push("Codex PostToolUse must match apply_patch");
		}
	}
	for (const file of [".claude/settings.json", ".codex/hooks.json"]) {
		try {
			if (!(await readFile(path.join(root, file), "utf8")).includes("scripts/agent_harness/hook.mjs")) {
				errors.push(`${file} does not target the shared hook`);
			}
		} catch {}
	}
	if (packageJson) {
		const scripts = new Set(Object.keys(packageJson.scripts ?? {}));
		for (const required of REQUIRED_SCRIPTS)
			if (!scripts.has(required)) errors.push(`package.json missing script: ${required}`);
		for (const [name, command] of Object.entries(packageJson.scripts ?? {})) {
			if (typeof command === "string" && command.includes(".claude/skills"))
				errors.push(`package script ${name} must use canonical .agents/skills`);
		}
	}
	const vitest = await readFile(path.join(root, "vitest.config.ts"), "utf8");
	if (!vitest.includes(".agents/skills/**/*.test.mjs") || vitest.includes(".claude/skills/**/*.test.mjs")) {
		errors.push("Vitest must execute canonical skill tests only");
	}
}

async function validateLegacy(root, errors) {
	for (const relative of LEGACY_PATHS)
		if (existsSync(path.join(root, relative))) errors.push(`legacy harness path still exists: ${relative}`);
	const activeFiles = ["AGENTS.md", "CLAUDE.md", "package.json"];
	for (const directory of [".agents", ".claude", ".codex", "docs/engineering", "scripts/agent_harness"]) {
		async function visit(relative) {
			for (const entry of await readdir(path.join(root, relative), { withFileTypes: true })) {
				const child = path.join(relative, entry.name);
				if (entry.isDirectory()) await visit(child);
				else if (entry.isFile()) activeFiles.push(child);
			}
		}
		if (existsSync(path.join(root, directory))) await visit(directory);
	}
	const bannedTerms = [
		[["super", "powers"].join(""), ":"].join(""),
		["im", "peccable"].join(""),
		[["code", "simplifier"].join("-"), ":"].join(""),
		["ui", "ux", "pro", "max"].join("-"),
		["subagent", "driven", "development"].join("-"),
		["test", "driven", "development"].join("-"),
		["verification", "before", "completion"].join("-"),
		["systematic", "debugging"].join("-"),
		["Web", "Search"].join(""),
		["op", "us"].join(""),
		["son", "net"].join(""),
		["hai", "ku"].join(""),
	];
	const banned = new RegExp(`(?:${bannedTerms.join("|")})`, "iu");
	for (const relative of activeFiles) {
		try {
			if (banned.test(await readFile(path.join(root, relative), "utf8")))
				errors.push(`third-party workflow dependency in ${relative}`);
		} catch {}
	}
}

export async function validateRepository(root = path.resolve(import.meta.dir, "../..")) {
	const errors = [];
	await validateInstructions(root, errors);
	await validateSkills(root, errors);
	await validateConfigs(root, errors);
	await validateLegacy(root, errors);
	return errors;
}

async function main() {
	const errors = await validateRepository();
	if (errors.length > 0) {
		process.stderr.write(`Harness validation failed:\n${errors.map((error) => `- ${error}`).join("\n")}\n`);
		process.exitCode = 1;
		return;
	}
	process.stdout.write("Harness validation passed.\n");
}

if (import.meta.main) {
	await main();
}
