import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { JSDOM } from "jsdom";
import { describe, expect, it } from "vitest";

const prototypePath = resolve(
	import.meta.dirname,
	"../docs/designs/specs/prototypes/page-agent-console-v2.html",
);
const railDomains = ["home", "markets", "research", "trading", "platform"] as const;

function loadDocument() {
	return new JSDOM(readFileSync(prototypePath, "utf-8")).window.document;
}

describe("page-agent-console-v2 prototype", () => {
	it("uses Chinese-first product copy for the default workspace chrome", () => {
		const document = loadDocument();
		const defaultViewText =
			document.querySelector("#default-view")?.textContent ?? "";
		const requiredCopy = [
			"智能体控制台",
			"运行中",
			"待审批",
			"已阻断",
			"产物",
			"新建计划",
			"计划 / 运行列表",
			"活动流",
			"发现",
			"运行检查器",
			"审批面板",
		];
		const demoEnglishCopy = [
			"Agent Console",
			"Running",
			"Waiting",
			"Blocked",
			"Artifacts",
			"Quality Run",
			"New Plan",
			"Plan / Run List",
			"Activity Stream",
			"Structured Findings",
			"Inspector",
			"Run Summary",
			"Agent Pipeline",
			"Tool Trace",
			"Approval Panel",
			"State Coverage",
		];

		for (const copy of requiredCopy) {
			expect(defaultViewText).toContain(copy);
		}
		for (const copy of demoEnglishCopy) {
			expect(defaultViewText).not.toContain(copy);
		}
	});

	it("keeps the default product surface inside design-cycle's three-zone structure", () => {
		const document = loadDocument();
		const defaultViewToggle =
			document.querySelector<HTMLInputElement>("#view-default");
		const defaultView = document.querySelector("#default-view");
		const statesGallery = document.querySelector("#states-gallery");
		const overlaysGallery = document.querySelector("#overlays-gallery");

		expect(defaultViewToggle?.checked).toBe(true);
		expect(defaultView).not.toBeNull();
		expect(statesGallery).not.toBeNull();
		expect(overlaysGallery).not.toBeNull();
		expect(defaultView?.querySelector(":scope > .agent-shell.studio-shell")).not.toBeNull();
	});

	it("matches mature Ditto shell chrome details used by neighboring studio pages", () => {
		const document = loadDocument();
		const defaultView = document.querySelector("#default-view");
		const shell = defaultView?.querySelector(".agent-shell");
		const railLinks = Array.from(
			defaultView?.querySelectorAll<HTMLAnchorElement>(".shell-rail .rail-icon") ?? [],
		);
		const utilityButtons = Array.from(
			defaultView?.querySelectorAll<HTMLElement>(
				"[data-header-utility-bar] [data-shell-utility]",
			) ?? [],
		).map((element) => element.dataset.shellUtility);
		const resizeSeparators = defaultView?.querySelectorAll("[data-resize-separator]");
		const statusBar = defaultView?.querySelector(
			":scope > .status-bar[data-contract-slot='status']",
		);

		expect(defaultView?.querySelector(".style-label")?.textContent).toContain(
			"Graphite Studio",
		);
		expect(shell?.getAttribute("data-resizable-panel-group")).toBe(
			"agent-console-workspace",
		);
		expect(railLinks).toHaveLength(5);
		expect(railLinks.map((link) => link.dataset.railDomain)).toEqual(railDomains);
		expect(
			railLinks.find((link) => link.classList.contains("active"))?.dataset.railDomain,
		).toBe("platform");
		expect(defaultView?.querySelectorAll(".shell-rail .rail-icon:not(a)")).toHaveLength(
			0,
		);
		expect(utilityButtons).toEqual([
			"command",
			"copilot",
			"notifications",
			"help",
			"theme",
			"density",
			"account",
		]);
		expect(resizeSeparators).toHaveLength(2);
		expect(statusBar?.textContent).toContain("智能体控制台");
		expect(
			defaultView?.querySelector(
				"[data-primary-answer-equivalent] [data-answer-judgment]",
			),
		).not.toBeNull();
	});

	it("exposes studio shell contract slots only in the default view", () => {
		const document = loadDocument();
		const defaultView = document.querySelector("#default-view");

		expect(defaultView).not.toBeNull();
		expect(
			defaultView?.querySelector(".list-panel[data-contract-slot='source']"),
		).not.toBeNull();
		expect(
			defaultView?.querySelector(".main-panel[data-contract-slot='main']"),
		).not.toBeNull();
		expect(
			defaultView?.querySelector(".inspector[data-contract-slot='inspector']"),
		).not.toBeNull();
		expect(
			document.querySelectorAll(
				"#states-gallery [data-contract-slot], #overlays-gallery [data-contract-slot]",
			),
		).toHaveLength(0);
	});

	it("renders the declared state and overlay coverage without inline styles", () => {
		const document = loadDocument();
		const ids = Array.from(document.querySelectorAll("[id]")).map(
			(element) => element.id,
		);

		expect(document.querySelectorAll("#states-gallery .gallery-card")).toHaveLength(
			39,
		);
		expect(document.querySelectorAll("#overlays-gallery .gallery-card")).toHaveLength(
			7,
		);
		expect(document.querySelectorAll(".overlay-radio")).toHaveLength(7);
		expect(document.querySelectorAll("[style]")).toHaveLength(0);
		expect(new Set(ids).size).toBe(ids.length);
	});
});
