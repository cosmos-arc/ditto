import { test, expect } from "bun:test";
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { checkWorkspace } from "../../dev/bun-workspace.mjs";

test("workspace checks reject stale locks and missing installed dependencies without writes", () => {
	const root = mkdtempSync(join(tmpdir(), "ditto-bun-check-"));
	try {
		const manifest = { name: "fixture", packageManager: `bun@${Bun.version}`, workspaces: [], devDependencies: { tool: "1.0.0" } };
		writeFileSync(join(root, "package.json"), JSON.stringify(manifest));
		const lock = { workspaces: { "": { devDependencies: {} } }, packages: { tool: ["tool@1.0.0"] } };
		writeFileSync(join(root, "bun.lock"), JSON.stringify(lock));
		const before = readFileSync(join(root, "bun.lock"), "utf8");
		expect(() => checkWorkspace(root)).toThrow("bun.lock is stale");
		expect(readFileSync(join(root, "bun.lock"), "utf8")).toBe(before);
		lock.workspaces[""].devDependencies = { tool: "1.0.0" };
		writeFileSync(join(root, "bun.lock"), JSON.stringify(lock));
		expect(() => checkWorkspace(root)).toThrow();
		mkdirSync(join(root, "node_modules/tool"), { recursive: true });
		writeFileSync(join(root, "node_modules/tool/package.json"), '{"version":"1.0.0"}');
		expect(() => checkWorkspace(root)).not.toThrow();
		rmSync(join(root, "bun.lock"));
		expect(() => checkWorkspace(root)).toThrow();
	} finally {
		rmSync(root, { recursive: true, force: true });
	}
});
