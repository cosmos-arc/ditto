import { readFileSync } from "node:fs";
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

function loadDocument(file: string): Document {
	return new JSDOM(readFileSync(resolve(prototypesDir, file), "utf8")).window.document;
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
