#!/usr/bin/env bun

import { readdir, readFile } from "node:fs/promises";
import path from "node:path";

const ROOT = path.resolve(import.meta.dir, "../..");
const SOURCE_EXTENSIONS = new Set([".js", ".jsx", ".ts", ".tsx"]);

async function sourceFiles(directory) {
	const files = [];
	for (const entry of await readdir(directory, { withFileTypes: true })) {
		const absolute = path.join(directory, entry.name);
		if (entry.isDirectory()) files.push(...(await sourceFiles(absolute)));
		else if (entry.isFile() && SOURCE_EXTENSIONS.has(path.extname(entry.name))) files.push(absolute);
	}
	return files;
}

const errors = [];
for (const relativeDirectory of ["src/components/ui", "src/lib"]) {
	for (const file of await sourceFiles(path.join(ROOT, relativeDirectory))) {
		const text = await readFile(file, "utf8");
		if (/from\s+["']@\/features\//u.test(text) || /from\s+["'](?:\.\.\/)+features\//u.test(text)) {
			errors.push(`${path.relative(ROOT, file)}: low-level code must not import feature internals`);
		}
	}
}

for (const file of await sourceFiles(path.join(ROOT, "src"))) {
	if (/\.(?:test|spec)\.(?:js|jsx|ts|tsx)$/u.test(file)) continue;
	const text = await readFile(file, "utf8");
	if (/@ts-ignore|@ts-expect-error/u.test(text))
		errors.push(`${path.relative(ROOT, file)}: TypeScript suppression is forbidden`);
	if (!file.includes(`${path.sep}styles${path.sep}design-tokens${path.sep}`) && /#[0-9a-fA-F]{3,8}\b/u.test(text)) {
		errors.push(`${path.relative(ROOT, file)}: hard-coded color must be a design token`);
	}
}

if (errors.length > 0) {
	process.stderr.write(`${errors.join("\n")}\n`);
	process.exit(1);
}
process.stdout.write("Frontend architecture checks passed.\n");
