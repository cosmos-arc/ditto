import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { JSDOM } from "jsdom";
import { describe, expect, it } from "vitest";

const root = process.cwd();
const prototypesDir = join(root, "docs/designs/specs/prototypes");
const contractsDir = join(root, "docs/contracts/pages");
const tokenStabilizationSpec = join(
	root,
	"docs/designs/specs/15_ditto_token_stabilization_spec.md",
);
const archivedPrototypeIds = new Set(["ai-overview", "ai-copilot"]);

type ManifestPage = {
	id: string;
	file: string;
	shellFamily?: string;
	status?: string;
	landing?: {
		overlayStatus?: string;
	};
};

type EditionManifest = {
	pages: ManifestPage[];
};

type PageContract = {
	id: string;
	prototypeRef: string;
	shellFamily: string;
	overlays?: Array<{ prototypeSelector: string }>;
};

function readJson<T>(path: string): T {
	return JSON.parse(readFileSync(path, "utf8")) as T;
}

function readManifest(): EditionManifest {
	return readJson<EditionManifest>(join(prototypesDir, ".edition-manifest.json"));
}

function isActiveRoutePrototype(page: ManifestPage): boolean {
	return (
		page.file?.startsWith("page-") &&
		page.file.endsWith(".html") &&
		page.id !== "token-showcase" &&
		!archivedPrototypeIds.has(page.id)
	);
}

function readPrototypeHtml(page: ManifestPage): string {
	return readFileSync(join(prototypesDir, page.file), "utf8");
}

function getOverlayIds(html: string): string[] {
	return [...new Set([...html.matchAll(/id="(overlay-[^"]+)"/g)].map((match) => match[1]))];
}

function readContracts(): PageContract[] {
	return readdirSync(contractsDir)
		.filter((file) => file.endsWith(".json"))
		.map((file) => readJson<PageContract>(join(contractsDir, file)));
}

function countMatches(value: string, pattern: RegExp): number {
	return [...value.matchAll(pattern)].length;
}

function getElementBodyById(html: string, id: string): string {
	const openTag = new RegExp(`<([a-z]+)[^>]*id="${id}"[^>]*>`, "i").exec(html);
	if (!openTag?.index) return "";

	const tagName = openTag[1];
	const bodyStart = openTag.index + openTag[0].length;
	const closeTag = new RegExp(`</${tagName}>`, "i");
	const closeMatch = closeTag.exec(html.slice(bodyStart));

	return closeMatch ? html.slice(bodyStart, bodyStart + closeMatch.index) : "";
}

function getFirstElementBody(html: string, selectorPattern: RegExp): string {
	const openTag = selectorPattern.exec(html);
	if (openTag?.index === undefined) return "";

	const fullOpenTag = openTag[0];
	const tagName = /<([a-z]+)/i.exec(fullOpenTag)?.[1];
	if (!tagName) return "";

	const bodyStart = openTag.index + fullOpenTag.length;
	const closeMatch = new RegExp(`</${tagName}>`, "i").exec(html.slice(bodyStart));
	return closeMatch ? html.slice(bodyStart, bodyStart + closeMatch.index) : "";
}

function getHeaderHtml(html: string): string {
	return getFirstElementBody(html, /<header\b[^>]*class="[^"]*shell-header[^"]*"[^>]*>/i);
}

function getRailHtml(html: string): string {
	return getFirstElementBody(html, /<nav\b[^>]*class="[^"]*shell-rail[^"]*"[^>]*>/i);
}

function readPrototypeDocument(page: ManifestPage): Document {
	return new JSDOM(readPrototypeHtml(page)).window.document;
}

const shellDomains = new Set(["home", "markets", "research", "trading", "platform"]);
const requiredHeaderUtilities = ["command", "copilot", "notifications", "help", "account"] as const;

describe("prototype design consistency", () => {
	it("keeps exactly 27 active route prototypes", () => {
		const activePages = readManifest().pages.filter(isActiveRoutePrototype);

		expect(activePages).toHaveLength(27);
	});

	it("keeps active route prototypes on the five IA domains", () => {
		const violations = readManifest()
			.pages.filter(isActiveRoutePrototype)
			.flatMap((page) => {
				const domain = /data-domain="([^"]+)"/.exec(readPrototypeHtml(page))?.[1];
				return domain && !shellDomains.has(domain) ? [`${page.id}:${domain}`] : [];
			});

		expect(violations).toEqual([]);
	});

	it("keeps rail limited to top-level product navigation", () => {
		const violations: string[] = [];

		for (const page of readManifest().pages.filter(isActiveRoutePrototype)) {
			const rail = getRailHtml(readPrototypeHtml(page));
			if (/id="density-toggle"|id="theme-toggle"|aria-label="设置"|aria-label="用户"/.test(rail)) {
				violations.push(page.id);
			}
		}

		expect(violations).toEqual([]);
	});

	it("exposes the same global header utilities in active route prototypes", () => {
		const violations: string[] = [];

		for (const page of readManifest().pages.filter(isActiveRoutePrototype)) {
			const header = getHeaderHtml(readPrototypeHtml(page));
			for (const utility of requiredHeaderUtilities) {
				if (!header.includes(`data-shell-utility="${utility}"`)) {
					violations.push(`${page.id}:${utility}`);
				}
			}
		}

		expect(violations).toEqual([]);
	});

	it("keeps theme and density controls inside view preferences menus", () => {
		const violations: string[] = [];

		for (const page of readManifest().pages.filter(isActiveRoutePrototype)) {
			const document = readPrototypeDocument(page);
			const looseHeaderControls = [
				...document.querySelectorAll(
					".shell-header [data-set-density], .shell-header [data-set-theme]",
				),
			].filter((element) => !element.closest("[data-view-preferences-menu]"));
			const looseRailControls = document.querySelectorAll(
				".shell-rail [data-set-density], .shell-rail [data-set-theme], .shell-rail #density-toggle, .shell-rail #theme-toggle",
			);

			if (looseHeaderControls.length > 0 || looseRailControls.length > 0) {
				violations.push(page.id);
			}
		}

		expect(violations).toEqual([]);
	});

	it("does not mark pages with overlay ids as overlayStatus none", () => {
		const offenders = readManifest()
			.pages.filter(isActiveRoutePrototype)
			.filter((page) => {
				const html = readPrototypeHtml(page);

				return /id="overlay-[^"]+"/.test(html) && page.landing?.overlayStatus === "none";
			})
			.map((page) => page.id);

		expect(offenders).toEqual([]);
	});

	it("registers every active prototype overlay in page contracts", () => {
		const contractByPrototype = new Map<string, Set<string>>();
		for (const contract of readContracts()) {
			const overlaySelectors = new Set(
				contract.overlays?.map((overlay) => overlay.prototypeSelector) ?? [],
			);
			contractByPrototype.set(contract.prototypeRef, overlaySelectors);
		}

		const missing: string[] = [];
		for (const page of readManifest().pages) {
			if (!isActiveRoutePrototype(page)) continue;

			const selectors =
				contractByPrototype.get(`docs/designs/specs/prototypes/${page.file}`) ?? new Set();

			for (const id of getOverlayIds(readPrototypeHtml(page))) {
				if (!selectors.has(`[data-overlay='${id}']`) && !selectors.has(`[data-overlay="${id}"]`)) {
					missing.push(`${page.id}:${id}`);
				}
			}
		}

		expect(missing).toEqual([]);
	});

	it("matches known shell family decisions from blueprints", () => {
		const expectedShellFamilies = new Map([
			["cross-market", "radar"],
			["agent-console", "studio"],
			["experiment-list", "catalog"],
		]);
		const manifest = readManifest();
		const contractById = new Map(readContracts().map((contract) => [contract.id, contract.shellFamily]));

		for (const [id, shellFamily] of expectedShellFamilies) {
			expect(manifest.pages.find((page) => page.id === id)?.shellFamily).toBe(shellFamily);
			expect(contractById.get(id)).toBe(shellFamily);
		}
	});

	it("marks overlay gallery specimens with data-overlay-ref", () => {
		const missing: string[] = [];

		for (const page of readManifest().pages) {
			if (!isActiveRoutePrototype(page)) continue;

			const html = readPrototypeHtml(page);
			const refs = new Set(
				[...html.matchAll(/data-overlay-ref="([^"]+)"/g)].map((match) => match[1]),
			);

			for (const id of getOverlayIds(html)) {
				if (!refs.has(id)) missing.push(`${page.id}:${id}`);
			}
		}

		expect(missing).toEqual([]);
	});

	it("does not introduce legacy overlay surface class names in active prototypes", () => {
		const legacyHits: string[] = [];

		for (const page of readManifest().pages) {
			if (!isActiveRoutePrototype(page)) continue;

			const html = readPrototypeHtml(page);
			for (const legacy of ["drawer-sheet", "modal-sheet", "overlay-sheet", "overlay-drawer"]) {
				if (html.includes(legacy)) legacyHits.push(`${page.id}:${legacy}`);
			}
		}

		expect(legacyHits).toEqual([]);
	});

	it("keeps prototype zones separated and singular", () => {
		const violations: string[] = [];

		for (const page of readManifest().pages) {
			if (!isActiveRoutePrototype(page)) continue;

			const html = readPrototypeHtml(page);
			for (const zoneId of ["default-view", "states-gallery", "overlays-gallery"]) {
				const count = countMatches(html, new RegExp(`id="${zoneId}"`, "g"));
				if (count !== 1) violations.push(`${page.id}:${zoneId}:${count}`);
			}

			const defaultView = getElementBodyById(html, "default-view");
			const statesGallery = getElementBodyById(html, "states-gallery");
			const overlaysGallery = getElementBodyById(html, "overlays-gallery");
			if (defaultView.includes("gallery-card")) violations.push(`${page.id}:default-gallery-card`);
			if (statesGallery.includes("overlay-surface")) violations.push(`${page.id}:states-overlay-surface`);
			if (overlaysGallery.includes("data-contract-slot")) {
				violations.push(`${page.id}:overlays-contract-slot`);
			}
		}

		expect(violations).toEqual([]);
	});

	it("documents the Edition v1 9-step typography scale as current token truth", () => {
		const spec = readFileSync(tokenStabilizationSpec, "utf8");
		const deprecatedTokenClaims = [
			/--font-size-11[^。\n]*(?:deprecated|forbidden|禁止|废弃)/i,
			/--font-size-18[^。\n]*(?:deprecated|forbidden|禁止|废弃)/i,
			/--font-size-20[^。\n]*(?:deprecated|forbidden|禁止|废弃)/i,
		];

		for (const claim of deprecatedTokenClaims) {
			expect(spec).not.toMatch(claim);
		}

		for (const token of [
			"--font-size-10",
			"--font-size-11",
			"--font-size-12",
			"--font-size-13",
			"--font-size-14",
			"--font-size-16",
			"--font-size-18",
			"--font-size-20",
			"--font-size-24",
		]) {
			expect(spec).toContain(token);
		}
	});

	it("keeps active route prototypes free of negative letter spacing", () => {
		const hits = readManifest()
			.pages.filter(isActiveRoutePrototype)
			.filter((page) => /letter-spacing\s*:\s*-/.test(readPrototypeHtml(page)))
			.map((page) => page.id);

		expect(hits).toEqual([]);
	});

	it("keeps bare rgba and direct oklch colors out of active prototype declarations", () => {
		const hits: string[] = [];

		for (const page of readManifest().pages) {
			if (!isActiveRoutePrototype(page)) continue;

			const lines = readPrototypeHtml(page).split("\n");
			lines.forEach((line, index) => {
				if (line.includes("rgba(")) hits.push(`${page.id}:${index + 1}:rgba`);
				if (
					line.includes("oklch(") &&
					!line.includes("oklch(from var(") &&
					!/--[a-z0-9-]+\s*:/i.test(line)
				) {
					hits.push(`${page.id}:${index + 1}:oklch`);
				}
			});
		}

		expect(hits).toEqual([]);
	});
});
