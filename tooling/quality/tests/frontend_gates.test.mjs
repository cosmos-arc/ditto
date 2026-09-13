import { describe, expect, test } from "bun:test";
import { mkdtemp, mkdir, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

import { runFrontendGates } from "../frontend_gates.mjs";

async function fixtureWeb(files) {
	const webRoot = await mkdtemp(path.join(tmpdir(), "frontend-gates-"));
	await mkdir(path.join(webRoot, "src"), { recursive: true });
	for (const [relative, content] of Object.entries(files)) {
		const target = path.join(webRoot, relative);
		await mkdir(path.dirname(target), { recursive: true });
		await writeFile(target, content, "utf8");
	}
	return webRoot;
}

describe("frontend regex gates", () => {
	test("clean sources pass", async () => {
		const root = await fixtureWeb({
			"src/features/markets/view.tsx": "export const V = () => <div className=\"bg-token-bg\" />;\n",
			"src/components/ui/card.tsx": "export const C = 1;\n",
		});
		expect(await runFrontendGates(root)).toEqual([]);
	});

	test("suppression, vite base url, sendBeacon, qualified network access and raw colors are reported", async () => {
		const root = await fixtureWeb({
			"src/lib/a.ts": "// @ts-expect-error\nexport const a = 1;\n",
			"src/features/b/b.ts": "export const u = import.meta.env.VITE_API_BASE_URL;\n",
			"src/features/c/c.ts": "export const s = navigator.sendBeacon;\n",
			"src/features/d/d.tsx": "export const color = \"#ff0000\";\n",
			"src/features/e/e.ts": "export const w = window.fetch(\"/x\");\n",
			"src/lib/f/f.ts": "export const s = globalThis[\"WebSocket\"];\n",
			"src/components/g/g.ts": "export const h = self.EventSource;\n",
			"src/lib/h/h.ts": "export const c = globalThis[\"fet\" + \"ch\"](\"/api\");\n",
			"src/lib/j/j.ts": "export const b = navigator[\"sendBeacon\"](\"/x\", {});\n",
			"src/lib/k/k.ts": "export const b = navigator[\"send\" + \"Beacon\"](\"/x\", {});\n",
		});
		const errors = await runFrontendGates(root);
		expect(errors.some((error) => error.includes("a.ts") && error.includes("suppression"))).toBe(true);
		expect(errors.some((error) => error.includes("b.ts") && error.includes("runtime config"))).toBe(true);
		expect(errors.some((error) => error.includes("c.ts") && error.includes("sendBeacon"))).toBe(true);
		expect(errors.some((error) => error.includes("d.tsx") && error.includes("raw hex"))).toBe(true);
		expect(errors.some((error) => error.includes("e.ts") && error.includes("qualified network global"))).toBe(
			true,
		);
		expect(errors.some((error) => error.includes("f.ts") && error.includes("qualified network global"))).toBe(
			true,
		);
		expect(errors.some((error) => error.includes("g.ts") && error.includes("qualified network global"))).toBe(
			true,
		);
		expect(errors.some((error) => error.includes("h.ts") && error.includes("qualified network global"))).toBe(
			true,
		);
		expect(errors.some((error) => error.includes("j.ts") && error.includes("qualified network global"))).toBe(
			true,
		);
		expect(errors.some((error) => error.includes("k.ts") && error.includes("qualified network global"))).toBe(
			true,
		);
	});

	test("canonical token css, tests and network capability zones are exempt", async () => {
		const root = await fixtureWeb({
			"src/styles/design-tokens/tokens.css": ":root { --bg: #ffffff; }\n",
			"src/features/e/e.test.ts": "export const color = \"#ff0000\";\nexport const w = window.fetch;\n",
			"src/api/transport.ts": "export const f = () => fetch(\"/x\");\nexport const w = window.fetch;\n",
			"src/mocks/handlers/mock-api.ts": "export const w = globalThis[\"WebSocket\"];\nexport const b = navigator.sendBeacon;\n",
			"src/lib/i/i.ts": "export const n = globalThis[dynamicName];\n",
			"src/lib/m/m.ts": "export const c = globalThis[\"crypto\"];\n",
		});
		expect(await runFrontendGates(root)).toEqual([]);
	});
});
