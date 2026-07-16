import { readdirSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { JSDOM } from "jsdom";
import { describe, expect, it } from "vitest";

const prototypesDir = resolve(import.meta.dirname, "../docs/designs/specs/prototypes");
const expertPages = ["page-home.html", "page-strategy-studio.html", "page-agent-console-v2.html"];
const rowContextMenuPages = [
	"page-watchlist.html",
	"page-signals-inbox.html",
	"page-strategy-list.html",
	"page-orders-ledger.html",
];
const complexDecisionBudgetPages = [
	"page-alpha-explorer.html",
	"page-agent-console-v2.html",
	"page-strategy-studio.html",
	"page-instrument-hub.html",
] as const;

const maxVisibleDecisionOptions = 4;

function loadDocument(file: string): Document {
	return new JSDOM(readFileSync(resolve(prototypesDir, file), "utf8")).window.document;
}

function readPrototypeFile(file: string): string {
	return readFileSync(resolve(prototypesDir, file), "utf8");
}

function readActivePrototypeFiles(): string[] {
	return readdirSync(prototypesDir).filter((file) => /^page-.*\.html$/.test(file));
}

function readActionIds(element: Element | null): string[] {
	return (element?.getAttribute("data-row-context-actions") ?? element?.getAttribute("data-command-context-actions") ?? "")
		.split(",")
		.map((action) => action.trim())
		.filter(Boolean);
}

describe("prototype expert efficiency", () => {
	it("makes the 5-second primary answer explicit on expert entry pages", () => {
		const missing = expertPages.filter(
			(file) => !loadDocument(file).querySelector("[data-primary-answer], [data-primary-answer-equivalent]"),
		);

		expect(missing).toEqual([]);
	});

	it("shows selected object state driving at least two regions where expected", () => {
		const violations = expertPages.filter(
			(file) => loadDocument(file).querySelectorAll("[data-selected-object-region]").length < 2,
		);

		expect(violations).toEqual([]);
	});

	it("keeps local search and filters distinct from global command", () => {
		const violations: string[] = [];

		for (const file of expertPages) {
			const document = loadDocument(file);
			for (const input of document.querySelectorAll("input.filter-search, input[type='search']")) {
				if (!input.getAttribute("data-local-search")) {
					violations.push(file);
				}
			}
		}

		expect(violations).toEqual([]);
	});

	it("keeps critical status markers readable without relying on color alone", () => {
		const violations: string[] = [];

		for (const file of expertPages) {
			const document = loadDocument(file);
			for (const status of document.querySelectorAll("[data-critical-status]")) {
				if (!status.querySelector("[data-danger-marker], [data-status-label]")) {
					violations.push(file);
				}
			}
		}

		expect(violations).toEqual([]);
	});

	it("keeps complex expert pages within a four-option first-screen decision budget", () => {
		const violations: string[] = [];

		for (const file of complexDecisionBudgetPages) {
			const document = loadDocument(file);
			const cluster = document.querySelector("[data-decision-cluster]");
			const options = cluster?.querySelectorAll("[data-decision-option]") ?? [];
			const overflow = cluster?.querySelector("[data-decision-overflow]");
			const primaryAnswer = document.querySelector("[data-primary-answer], [data-primary-answer-equivalent]");

			if (!cluster) {
				violations.push(`${file}:decision-cluster:missing`);
				continue;
			}
			if (!primaryAnswer) {
				violations.push(`${file}:primary-answer:missing`);
			}
			if (options.length === 0) {
				violations.push(`${file}:decision-options:missing`);
			}
			if (options.length > maxVisibleDecisionOptions) {
				violations.push(`${file}:decision-options:${options.length}`);
			}
			if (options.length === maxVisibleDecisionOptions && !overflow) {
				violations.push(`${file}:overflow:missing`);
			}
			for (const [index, option] of [...options].entries()) {
				const text = option.textContent?.replace(/\s+/g, " ").trim() ?? "";
				const label = option.getAttribute("aria-label") ?? "";
				if (!text && !label) {
					violations.push(`${file}:decision-option:${index + 1}:name`);
				}
			}
		}

		expect(violations).toEqual([]);
	});

	it("keeps complex page inspectors focused on current-decision evidence by default", () => {
		const violations: string[] = [];

		for (const file of complexDecisionBudgetPages) {
			const document = loadDocument(file);
			const defaultOpenSections = document.querySelectorAll(
				"[data-decision-evidence][data-default-open='true'], details[data-decision-evidence][open]",
			);
			const backgroundSections = document.querySelectorAll(
				"[data-background-evidence][data-default-open='true'], details[data-background-evidence][open]",
			);

			if (defaultOpenSections.length < 1) {
				violations.push(`${file}:decision-evidence:missing`);
			}
			if (defaultOpenSections.length > 2) {
				violations.push(`${file}:decision-evidence:${defaultOpenSections.length}`);
			}
			if (backgroundSections.length > 0) {
				violations.push(`${file}:background-open:${backgroundSections.length}`);
			}
		}

		expect(violations).toEqual([]);
	});

	it("covers stale and selected Home states in the state gallery", () => {
		const document = loadDocument("page-home.html");
		const states = new Set(
			Array.from(document.querySelectorAll("#states-gallery [data-state]")).map((element) =>
				element.getAttribute("data-state"),
			),
		);

		expect(states.has("stale")).toBe(true);
		expect(states.has("selected")).toBe(true);
	});

	it("keeps Home default view free of prototype state gallery fixtures", () => {
		const document = loadDocument("page-home.html");
		const defaultView = document.querySelector("#default-view");
		const leakedFixtures = Array.from(
			defaultView?.querySelectorAll(
				[
					".state-stale-variant",
					".state-variant-content",
					'[data-state="stale"][aria-label*="过期状态"]',
					'[data-state="selected"][aria-label*="选中状态"]',
				].join(", "),
			) ?? [],
		).map((element) => element.getAttribute("data-contract-slot") ?? element.className);

		expect(leakedFixtures).toEqual([]);
	});

	it("declares a safe narrow-viewport strategy for desktop-only prototypes", () => {
		const layoutCss = readPrototypeFile("shared/layout-shell.css");
		const interactionsJs = readPrototypeFile("shared/prototype-interactions.js");

		expect(layoutCss).toContain("--prototype-min-desktop-width: 1024px;");
		expect(layoutCss).toContain(".prototype-viewport-guard");
		expect(layoutCss).toContain("@media (max-width: 767px)");
		expect(interactionsJs).toContain("PrototypeViewportGuard");
		expect(interactionsJs).toContain("当前原型面向桌面工作台");
	});

	it("keeps Agent Console V2 top-level navigation to four primary tabs plus overflow", () => {
		const document = loadDocument("page-agent-console-v2.html");
		const primaryTabs = document.querySelectorAll(".agent-tabs .tab:not(.tab-overflow)");
		const overflow = document.querySelector(".agent-tabs .tab-overflow[aria-haspopup='menu']");

		expect(primaryTabs.length).toBeLessThanOrEqual(4);
		expect(overflow?.getAttribute("aria-label")).toContain("更多控制台视图");
	});

	it("keeps active prototype cards and lists free of thick directional side stripes", () => {
		const violations: string[] = [];
		const sideStripePattern =
			/(border-(?:left|right):\s*(?:[2-9]|[0-9]{2,})px|border-left:\s*var\(--accent|box-shadow:\s*inset\s*-?(?:[2-9]|[0-9]{2,})px\s+0)/;

		for (const file of readActivePrototypeFiles()) {
			const lines = readPrototypeFile(file).split("\n");
			lines.forEach((line, index) => {
				const sortTriangle =
					file === "page-research.html" &&
					/border-(?:left|right):\s*3px\s+solid\s+transparent/.test(line) &&
					lines.slice(index, index + 3).some((candidate) => candidate.includes("border-bottom: 4px solid"));

				if (sideStripePattern.test(line) && !sortTriangle) {
					violations.push(`${file}:${index + 1}:${line.trim()}`);
				}
			});
		}

		expect(violations).toEqual([]);
	});

	it("keeps sampled material effects within the freeze budget", () => {
		const sampledFiles = [
			"page-home.html",
			"page-trading-overview.html",
			"page-strategy-studio.html",
			"page-risk-center.html",
			"page-agent-console-v2.html",
			"page-orders-ledger.html",
			"shared/layout-shell.css",
		];
		const violations = sampledFiles.flatMap((file) => {
			const content = readPrototypeFile(file);
			const overBlur = content.match(/backdrop-filter:\s*blur\((?:1[3-9]|[2-9][0-9])px/);
			const frostedSaturate = content.match(/backdrop-filter:[^;]*saturate\(/);
			const ambientShellGradient = content.match(
				/linear-gradient\(180deg,\s*color-mix\(in oklch,\s*var\(--brand-accent\)[^;]+var\(--surface-app\)/,
			);

			return [
				overBlur ? `${file}:over-blur:${overBlur[0]}` : "",
				frostedSaturate ? `${file}:frosted-saturate:${frostedSaturate[0]}` : "",
				ambientShellGradient ? `${file}:ambient-shell-gradient` : "",
			].filter(Boolean);
		});

		expect(violations).toEqual([]);
	});

	it("exposes Studio and Agent slots needed for React parity", () => {
		const requiredSlots = new Map([
			["page-strategy-studio.html", ["main", "sidebar", "inspector", "activity-log", "status"]],
			["page-agent-console-v2.html", ["header", "tabs", "source", "main", "inspector", "status"]],
		]);
		const violations: string[] = [];

		for (const [file, slots] of requiredSlots) {
			const document = loadDocument(file);
			for (const slot of slots) {
				if (!document.querySelector(`[data-contract-slot="${slot}"]`)) {
					violations.push(`${file}:${slot}`);
				}
			}
		}

		expect(violations).toEqual([]);
	});

	it("keeps row context menu core actions aligned with command palette context actions", () => {
		const violations: string[] = [];

		for (const file of rowContextMenuPages) {
			const document = loadDocument(file);
			const commandContext = document.querySelector("[data-command-context-actions]");
			const row = document.querySelector(
				"[data-row-context-menu-ready] tbody tr[data-row-context-actions], [data-row-context-menu-ready] tbody tr[data-command-context-actions]",
			);
			const commandActions = readActionIds(commandContext);
			const rowActions = readActionIds(row);

			if (!commandActions.length || rowActions.join("|") !== commandActions.join("|")) {
				violations.push(`${file}:${rowActions.join(",") || "missing-row-actions"}`);
			}
		}

		expect(violations).toEqual([]);
	});
});
