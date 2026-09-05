import * as jestDomMatchers from "@testing-library/jest-dom/matchers";
import { cleanup } from "@testing-library/react";
import { afterAll, afterEach, beforeAll, beforeEach, expect, vi } from "vitest";
import { installRuntimeConfig } from "@/api/runtime-config";
import { server } from "@/mocks/server";

// The matcher-only entry point is workspace-isolation safe: unlike the
// convenience `/vitest` entry point, it does not resolve Vitest from inside
// jest-dom's package directory.
expect.extend(jestDomMatchers);

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
	installRuntimeConfig({ schemaVersion: 1, runtime: "mock", apiOrigin: "" }, { production: false });
	vi.stubEnv("VITE_USE_MOCK", "true");
});

/* ── MSW + cleanup ── */

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));

afterEach(() => {
	server.resetHandlers();
	cleanup();
});

afterAll(() => server.close());
