#!/usr/bin/env bun

import { readdir, readFile, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { summarizePageCompletion } from "./product-recovery-core.mjs";

const ROOT = resolve(import.meta.dirname, "..");
const CONTRACTS_DIR = resolve(ROOT, "contracts/pages");
const EDITION_MANIFEST_PATH = resolve(ROOT, "prototype/.edition-manifest.json");
const OUTPUT_PATH = resolve(ROOT, "docs/plans/2026-08-29-product-completion-board.md");

const mark = (value) => (value === "verified" || value === "wired" ? "✅" : "⬜");

async function renderBoard() {
	const files = (await readdir(CONTRACTS_DIR)).filter((file) => file.endsWith(".contract.json")).sort();
	const contracts = await Promise.all(
		files.map(async (file) => JSON.parse(await readFile(resolve(CONTRACTS_DIR, file), "utf-8"))),
	);
	const editionManifest = JSON.parse(await readFile(EDITION_MANIFEST_PATH, "utf-8"));
	for (const route of editionManifest.reactOnlyRoutes ?? []) {
		contracts.push({
			...route,
			route: route.route,
			landing: route.landing ?? { reactRouteStatus: route.status },
			states: route.states ?? { universal: [], pageSpecific: [] },
			overlays: route.overlays ?? [],
		});
	}
	contracts.sort((left, right) => left.route.localeCompare(right.route));
	const rows = contracts.map((contract) => {
		const status = summarizePageCompletion(contract);
		const overlay = status.overlays.total === 0 ? "✅ none" : `${status.overlays.concrete}/${status.overlays.total}`;
		return `| \`${contract.route}\` | ${mark(status.route)} | ${mark(status.liveData)} | ${mark(status.visualParity)} | ${status.states.declared} declared / ${status.states.testRefs} tests | ${overlay} | ${mark(status.workflow)} |`;
	});
	const verified = contracts.filter((contract) => summarizePageCompletion(contract).workflow === "verified").length;

	return `# Ditto 产品页面完成看板

> 生成日期：2026-08-29
> 生成命令：\`bun run audit:product-board\`
> 口径：只认合同与可执行证据。\`prototypeVerified\` 不等于 \`reactParityVerified\`；workflow 只有在 route、live data、React parity、通用状态测试和 overlay 全部闭环时才为 ✅。

当前严格闭环：**${verified}/${contracts.length}**。⬜ 表示尚无足够证据，不代表路由不存在。

| Route | Route | Live data | Visual parity | States | Overlays | Workflow |
|---|---:|---:|---:|---:|---:|---:|
${rows.join("\n")}
`;
}

const output = await renderBoard();
if (process.argv.includes("--check")) {
	const current = await readFile(OUTPUT_PATH, "utf-8").catch(() => "");
	if (current !== output) {
		console.error("[product-board] Completion board is stale. Run bun run audit:product-board.");
		process.exit(1);
	}
	console.log("[product-board] Completion board is current.");
} else {
	await writeFile(OUTPUT_PATH, output);
	console.log("[product-board] Completion board updated.");
}
