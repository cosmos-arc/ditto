import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { JSDOM } from "jsdom";
import { describe, expect, it } from "vitest";

const prototypePath = resolve(
	import.meta.dirname,
	"../docs/designs/specs/prototypes/page-ai-overview.html",
);

function loadPage() {
	const html = readFileSync(prototypePath, "utf-8");
	return new JSDOM(html).window.document;
}

function pageStyleText(document: Document) {
	return Array.from(document.querySelectorAll("style"))
		.map((style) => style.textContent ?? "")
		.join("\n");
}

describe("page-ai-overview prototype", () => {
	it("keeps tab controls and panels in one shared interaction scope", () => {
		const document = loadPage();
		const tabScope = document.querySelector(".ai-main[data-tabs='ai-tabs']");

		expect(tabScope).not.toBeNull();
		expect(tabScope?.querySelectorAll("[data-tab-target]")).toHaveLength(3);
		expect(tabScope?.querySelectorAll("[data-tab-panel]")).toHaveLength(3);
		expect(tabScope?.querySelector("[data-tab-panel='overview']")).not.toBeNull();
		expect(tabScope?.querySelector("[data-tab-panel='models']")).not.toBeNull();
		expect(tabScope?.querySelector("[data-tab-panel='signals']")).not.toBeNull();
	});

	it("makes header and action CTAs real toast triggers", () => {
		const document = loadPage();

		expect(document.querySelectorAll("label[for='overlay-new-session-toast']")).toHaveLength(2);
		expect(document.querySelectorAll("label[for='overlay-new-plan-toast']")).toHaveLength(2);
		expect(document.querySelector("#overlay-new-session-toast")).not.toBeNull();
		expect(document.querySelector("#overlay-new-plan-toast")).not.toBeNull();
		expect(document.querySelector("[data-overlay='overlay-new-session-toast']")).not.toBeNull();
		expect(document.querySelector("[data-overlay='overlay-new-plan-toast']")).not.toBeNull();
	});

	it("uses whole-rail scrolling for AI sidebar sections instead of clipped micro-scroll panels", () => {
		const document = loadPage();
		const styleText = pageStyleText(document);

		expect(styleText).toContain(".ai-shell .context-rail");
		expect(styleText).toContain("overflow: visible");
		expect(styleText).toContain(".ai-shell .context-section");
		expect(styleText).toContain("flex: 0 0 auto");
		expect(styleText).toContain(".ai-shell .context-section-body");
	});

	it("preserves declared state and overlay coverage", () => {
		const document = loadPage();

		expect(document.querySelectorAll("#states-gallery .gallery-card")).toHaveLength(12);
		expect(document.querySelectorAll("#overlays-gallery .gallery-card")).toHaveLength(2);
		expect(document.querySelectorAll(".overlay-radio")).toHaveLength(2);
	});

	it("does not use inline styles in the prototype markup", () => {
		const document = loadPage();

		expect(document.querySelectorAll("[style]")).toHaveLength(0);
	});
});
