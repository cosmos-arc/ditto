import { readFileSync } from "node:fs";

const expected = readFileSync(new URL("../../.node-version", import.meta.url), "utf8").trim();
if (process.versions.bun || process.versions.node !== expected) {
	throw new Error(`Node mismatch: expected ${expected}, got ${process.version}`);
}
