import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { JSDOM } from "jsdom";
import { describe, expect, it } from "vitest";

const root = process.cwd();
const prototypesDir = join(root, "docs/designs/specs/prototypes");

const highRiskPages = [
	"page-home.html",
	"page-trading-overview.html",
	"page-risk-center.html",
	"page-agent-console-v2.html",
	"page-backtest-result.html",
	"page-signals-inbox.html",
	"page-orders-ledger.html",
	"page-strategy-list.html",
	"page-platform-settings.html",
	"page-universe-list.html",
] as const;

function loadDocument(file: string): Document {
	return new JSDOM(readFileSync(join(prototypesDir, file), "utf8")).window.document;
}

function overlayName(element: Element): string {
	return element.getAttribute("aria-label") ?? element.id ?? element.textContent?.replace(/\s+/g, " ").trim().slice(0, 80) ?? "unknown";
}

describe("prototype high-risk confirmation contract", () => {
	it("keeps every declared high-risk confirmation auditable and recoverable", () => {
		const failures: string[] = [];

		for (const file of highRiskPages) {
			const document = loadDocument(file);
			const confirmations = [...document.querySelectorAll<HTMLElement>("[data-high-risk-confirmation]")];

			if (confirmations.length === 0) {
				failures.push(`${file}: missing [data-high-risk-confirmation]`);
				continue;
			}

			for (const confirmation of confirmations) {
				const name = overlayName(confirmation);
				const requiredSelectors = [
					"[data-impact-summary]",
					"[data-before-after]",
					"[data-evidence-chain]",
					"[data-audit-record]",
					"[data-recovery-path]",
					"[data-cancel-control]",
					"[data-confirm-control]",
				];

				for (const selector of requiredSelectors) {
					if (!confirmation.querySelector(selector)) {
						failures.push(`${file}:${name}: missing ${selector}`);
					}
				}
			}
		}

		expect(failures).toEqual([]);
	});

	it("does not leave superseded root Agent Console in active high-risk scope", () => {
		const rootFiles = readdirSync(prototypesDir).filter((file) => /^page-.*\.html$/.test(file));
		const failures = rootFiles.filter((file) => file === "page-agent-console.html");

		expect(failures).toEqual([]);
	});
});
