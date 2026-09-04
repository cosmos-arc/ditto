import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterAll, afterEach, beforeAll, beforeEach, vi } from "vitest";
import { server } from "@/mocks/server";

/* ── IntersectionObserver stub (jsdom lacks native support) ── */

class StubIntersectionObserver implements IntersectionObserver {
	readonly root: Element | null = null;
	readonly rootMargin: string = "";
	readonly thresholds: ReadonlyArray<number> = [];
	readonly scrollMargin: string = "";

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

beforeEach(() => {
	vi.stubEnv("VITE_USE_MOCK", "true");
});

/* ── MSW + cleanup ── */

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));

afterEach(() => {
	server.resetHandlers();
	cleanup();
});

afterAll(() => server.close());
