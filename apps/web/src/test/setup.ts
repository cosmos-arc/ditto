import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, beforeAll, afterAll, vi } from "vitest";
import { server } from "@/mocks/server";

/* ── IntersectionObserver stub (jsdom lacks native support) ── */

class StubIntersectionObserver implements IntersectionObserver {
	readonly root: Element | null = null;
	readonly rootMargin: string = "";
	readonly thresholds: ReadonlyArray<number> = [];
	readonly scrollMargin: string = "";

	constructor(_callback: IntersectionObserverCallback) {
		// noop — jsdom has no layout engine
	}

	disconnect() {}
	observe() {}
	takeRecords(): IntersectionObserverEntry[] {
		return [];
	}
	unobserve() {}
}

beforeAll(() => {
	vi.stubGlobal("IntersectionObserver", StubIntersectionObserver);
});

/* ── MSW + cleanup ── */

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));

afterEach(() => {
	server.resetHandlers();
	cleanup();
});

afterAll(() => server.close());
