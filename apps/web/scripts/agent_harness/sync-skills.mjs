#!/usr/bin/env bun

import { cp, mkdir, readdir, readFile, rm } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(SCRIPT_DIR, "../..");
const DEFAULT_SOURCE = path.join(ROOT, ".agents/skills");
const DEFAULT_MIRROR = path.join(ROOT, ".claude/skills");

async function treeFiles(root) {
	const files = new Map();

	async function visit(directory) {
		for (const entry of await readdir(directory, { withFileTypes: true })) {
			const absolute = path.join(directory, entry.name);
			if (entry.isDirectory()) {
				await visit(absolute);
			} else if (entry.isFile()) {
				files.set(path.relative(root, absolute).split(path.sep).join("/"), await readFile(absolute));
			}
		}
	}

	try {
		await visit(root);
	} catch (error) {
		if (error?.code !== "ENOENT") {
			throw error;
		}
	}
	return files;
}

export async function compareTrees(source = DEFAULT_SOURCE, mirror = DEFAULT_MIRROR) {
	const [sourceFiles, mirrorFiles] = await Promise.all([treeFiles(source), treeFiles(mirror)]);
	const errors = [];

	for (const [relative, content] of sourceFiles) {
		if (!mirrorFiles.has(relative)) {
			errors.push(`missing from Claude mirror: ${relative}`);
		} else if (!content.equals(mirrorFiles.get(relative))) {
			errors.push(`content drift: ${relative}`);
		}
	}
	for (const relative of mirrorFiles.keys()) {
		if (!sourceFiles.has(relative)) {
			errors.push(`extra in Claude mirror: ${relative}`);
		}
	}
	return errors.sort();
}

export async function syncTrees(source = DEFAULT_SOURCE, mirror = DEFAULT_MIRROR) {
	await rm(mirror, { recursive: true, force: true });
	await mkdir(path.dirname(mirror), { recursive: true });
	await cp(source, mirror, { recursive: true });
}

async function main() {
	if (process.argv.includes("--check")) {
		const errors = await compareTrees();
		if (errors.length > 0) {
			process.stderr.write(`${errors.join("\n")}\n`);
			process.exitCode = 1;
			return;
		}
		process.stdout.write("Agent skill mirror is synchronized.\n");
		return;
	}

	await syncTrees();
	process.stdout.write("Synchronized .agents/skills to .claude/skills.\n");
}

if (import.meta.main) {
	await main();
}
