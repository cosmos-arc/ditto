import { afterEach, describe, expect, test } from "bun:test";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

import { classifyDiff, extractEditedFiles, policyViolation, stopDecision, verificationCommands } from "../hook.mjs";

const temporaryDirectories = [];

afterEach(async () => {
	await Promise.all(temporaryDirectories.splice(0).map((directory) => rm(directory, { recursive: true, force: true })));
});

describe("command policy", () => {
	test("blocks destructive or non-Bun project mutations", () => {
		const blocked = [
			["git commit -m change", "main"],
			["git -C . push origin main", "main"],
			["git push origin feature --force-with-lease", "feature"],
			["git reset --hard HEAD~1", "feature"],
			["git commit --no-verify -m change", "feature"],
			["rm -r -f dist", "feature"],
			["rm dist -rf", "feature"],
			["npm install react", "feature"],
			["npm ci", "feature"],
			["yarn add react", "feature"],
			["pnpm remove react", "feature"],
		];

		for (const [command, branch] of blocked) {
			expect(policyViolation(command, branch)).not.toBeNull();
		}
	});

	test("allows safe project commands", () => {
		for (const command of ["bun run check", "bunx biome check .", "git status -sb", "bunx vitest run src"]) {
			expect(policyViolation(command, "feature")).toBeNull();
		}
	});
});

describe("edited path extraction", () => {
	test("reads Claude and Codex payloads", () => {
		const root = "/repo";
		expect(extractEditedFiles({ tool_input: { file_path: "src/app.tsx" } }, root)).toEqual(["src/app.tsx"]);
		expect(
			extractEditedFiles(
				{
					tool_input: {
						command:
							"*** Begin Patch\n*** Update File: src/app.tsx\n*** Add File: src/new.ts\n*** Move to: src/moved.ts\n*** End Patch",
					},
				},
				root,
			),
		).toEqual(["src/app.tsx", "src/moved.ts", "src/new.ts"]);
	});
});

describe("changed-scope gate", () => {
	test("classifies documentation, tests, styles, harness, source, and dependencies", () => {
		expect(classifyDiff(["docs/engineering/testing.md"])).toBe("docs");
		expect(classifyDiff(["src/lib/api-client.test.ts"])).toBe("tests");
		expect(classifyDiff(["src/styles/design-tokens/tokens-base.css"])).toBe("styles");
		expect(classifyDiff(["DESIGN.md"])).toBe("styles");
		expect(classifyDiff(["AGENTS.md", ".agents/skills/ditto-app-dev/SKILL.md"])).toBe("harness");
		expect(classifyDiff(["AGENTS.md", "src/lib/api-client.ts"])).toBe("source");
		expect(classifyDiff(["AGENTS.md", "src/lib/api-client.test.ts"])).toBe("source");
		expect(classifyDiff(["src/lib/api-client.ts"])).toBe("source");
		expect(classifyDiff(["package.json"])).toBe("source");
	});

	test("keeps test-only checks scoped and non-mutating", () => {
		const commands = verificationCommands("tests", ["src/lib/api-client.test.ts"]);
		const flattened = commands.map((command) => command.join(" "));
		expect(flattened).toContain("bunx biome check src/lib/api-client.test.ts");
		expect(flattened.some((command) => command.includes("vitest run src/lib/api-client.test.ts"))).toBe(true);
		expect(flattened.every((command) => !command.includes("--write"))).toBe(true);
	});

	test("blocks the first failed Stop and reports the retry", async () => {
		const root = await mkdtemp(path.join(tmpdir(), "ditto-app-hook-"));
		temporaryDirectories.push(root);
		const verifier = async () => ({ ok: false, summary: "fixture failure" });

		const first = await stopDecision({ payload: {}, root, files: ["AGENTS.md"], digest: "same", verifier });
		const second = await stopDecision({
			payload: { stop_hook_active: true },
			root,
			files: ["AGENTS.md"],
			digest: "same",
			verifier,
		});

		expect(first.decision).toBe("block");
		expect(first.reason).toContain("fixture failure");
		expect(second.decision).toBeUndefined();
		expect(second.systemMessage).toContain("must report");
	});

	test("caches a successful receipt for an identical diff", async () => {
		const root = await mkdtemp(path.join(tmpdir(), "ditto-app-hook-"));
		temporaryDirectories.push(root);
		let calls = 0;
		const verifier = async () => {
			calls += 1;
			return { ok: true, summary: "ok" };
		};

		const options = { payload: {}, root, files: ["AGENTS.md"], digest: "same", verifier };
		expect(await stopDecision(options)).toEqual({});
		expect(await stopDecision(options)).toEqual({});
		expect(calls).toBe(1);
	});
});
