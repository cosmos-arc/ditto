import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { readFileSync } from "node:fs";

const expected = readFileSync(new URL("../../.node-version", import.meta.url), "utf8").trim();
if (process.versions.bun || process.versions.node !== expected) {
	throw new Error(`Node mismatch: expected ${expected}, got ${process.version}`);
}

const check = spawnSync("bun", [fileURLToPath(new URL("./bun-workspace.mjs", import.meta.url))], { stdio: "inherit" });
if (check.error) throw check.error;
if (check.status !== 0) process.exit(check.status ?? 1);
