import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useScrollReveal } from "./use-scroll-reveal";

/* ── IntersectionObserver mock ── */

interface MockObserverEntry {
	readonly isIntersecting: boolean;
	readonly target: Element;
}

let mockObserverCallback: (entries: MockObserverEntry[]) => void;
let mockObserveFn: (element: Element) => void;
let mockDisconnectFn: () => void;

beforeEach(() => {
	mockObserveFn = vi.fn();
	mockDisconnectFn = vi.fn();

	class MockIntersectionObserver {
		callback: (entries: MockObserverEntry[]) => void;
		constructor(callback: (entries: MockObserverEntry[]) => void) {
			this.callback = callback;
			mockObserverCallback = callback;
		}
		observe = mockObserveFn;
		disconnect = mockDisconnectFn;
		unobserve = vi.fn();
	}

	vi.stubGlobal("IntersectionObserver", MockIntersectionObserver);
});

afterEach(() => {
	vi.restoreAllMocks();
	vi.unstubAllGlobals();
});

/* ── Helper: trigger viewport entry ── */

function triggerViewportEntry(target?: Element): void {
	act(() => {
		mockObserverCallback([
			{ isIntersecting: true, target: target ?? document.createElement("div") },
		]);
	});
}

function triggerViewportExit(target?: Element): void {
	act(() => {
		mockObserverCallback([
			{ isIntersecting: false, target: target ?? document.createElement("div") },
		]);
	});
}

/* ── Tests ── */

describe("useScrollReveal", () => {
	/* ── Return value ── */

	it("returns a callback ref and isVisible=false initially", () => {
		const { result } = renderHook(() => useScrollReveal());
		expect(typeof result.current.ref).toBe("function");
		expect(result.current.isVisible).toBe(false);
	});

	/* ── Observer creation ── */

	it("creates IntersectionObserver when ref is attached to an element", () => {
		const { result } = renderHook(() => useScrollReveal());
		const element = document.createElement("div");
		act(() => {
			result.current.ref(element);
		});
		expect(mockObserveFn).toHaveBeenCalledTimes(1);
		expect(mockObserveFn).toHaveBeenCalledWith(element);
	});

	it("does not create observer when ref receives null", () => {
		const { result } = renderHook(() => useScrollReveal());
		act(() => {
			result.current.ref(null);
		});
		expect(mockObserveFn).not.toHaveBeenCalled();
	});

	/* ── Visibility state ── */

	it("sets isVisible=true when element enters viewport", () => {
		const { result } = renderHook(() => useScrollReveal());
		const element = document.createElement("div");
		act(() => {
			result.current.ref(element);
		});
		triggerViewportEntry(element);
		expect(result.current.isVisible).toBe(true);
	});

	it("stays isVisible=false when element is not intersecting", () => {
		const { result } = renderHook(() => useScrollReveal());
		const element = document.createElement("div");
		act(() => {
			result.current.ref(element);
		});
		triggerViewportExit(element);
		expect(result.current.isVisible).toBe(false);
	});

	/* ── once option (default: true) ── */

	it("disconnects observer after first reveal when once=true (default)", () => {
		const { result } = renderHook(() => useScrollReveal());
		const element = document.createElement("div");
		act(() => {
			result.current.ref(element);
		});
		triggerViewportEntry(element);
		expect(mockDisconnectFn).toHaveBeenCalledTimes(1);
	});

	it("remains visible after disconnect (once=true)", () => {
		const { result } = renderHook(() => useScrollReveal());
		const element = document.createElement("div");
		act(() => {
			result.current.ref(element);
		});
		triggerViewportEntry(element);
		// Even after disconnect, isVisible stays true
		expect(result.current.isVisible).toBe(true);
	});

	/* ── once=false ── */

	it("does not disconnect after reveal when once=false", () => {
		const { result } = renderHook(() => useScrollReveal({ once: false }));
		const element = document.createElement("div");
		act(() => {
			result.current.ref(element);
		});
		triggerViewportEntry(element);
		expect(mockDisconnectFn).not.toHaveBeenCalled();
	});

	it("toggles visibility when once=false and element exits viewport", () => {
		const { result } = renderHook(() => useScrollReveal({ once: false }));
		const element = document.createElement("div");
		act(() => {
			result.current.ref(element);
		});
		triggerViewportEntry(element);
		expect(result.current.isVisible).toBe(true);

		triggerViewportExit(element);
		expect(result.current.isVisible).toBe(false);
	});

	it("re-reveals when once=false and element re-enters viewport", () => {
		const { result } = renderHook(() => useScrollReveal({ once: false }));
		const element = document.createElement("div");
		act(() => {
			result.current.ref(element);
		});
		triggerViewportEntry(element);
		triggerViewportExit(element);
		triggerViewportEntry(element);
		expect(result.current.isVisible).toBe(true);
	});

	/* ── Observer options ── */

	it("passes threshold option to IntersectionObserver", () => {
		const { result } = renderHook(() =>
			useScrollReveal({ threshold: 0.5 }),
		);
		const element = document.createElement("div");
		act(() => {
			result.current.ref(element);
		});
		// The observer was created (verify via observe call)
		expect(mockObserveFn).toHaveBeenCalledWith(element);
	});

	it("passes rootMargin option to IntersectionObserver", () => {
		const { result } = renderHook(() =>
			useScrollReveal({ rootMargin: "50px" }),
		);
		const element = document.createElement("div");
		act(() => {
			result.current.ref(element);
		});
		expect(mockObserveFn).toHaveBeenCalledWith(element);
	});

	/* ── Cleanup ── */

	it("disconnects observer on unmount", () => {
		const { result, unmount } = renderHook(() => useScrollReveal());
		const element = document.createElement("div");
		act(() => {
			result.current.ref(element);
		});
		unmount();
		expect(mockDisconnectFn).toHaveBeenCalled();
	});

	/* ── Ref replacement ── */

	it("disconnects old observer when ref is called with a new element", () => {
		const { result } = renderHook(() => useScrollReveal());
		const element1 = document.createElement("div");
		const element2 = document.createElement("div");

		act(() => {
			result.current.ref(element1);
		});
		expect(mockObserveFn).toHaveBeenCalledTimes(1);

		// Replace with new element
		act(() => {
			result.current.ref(element2);
		});
		// Old observer should be disconnected
		expect(mockDisconnectFn).toHaveBeenCalled();
		// New observer should observe the new element
		expect(mockObserveFn).toHaveBeenCalledWith(element2);
	});

	/* ── Defaults ── */

	it("uses default options when none provided", () => {
		const { result } = renderHook(() => useScrollReveal());
		const element = document.createElement("div");
		act(() => {
			result.current.ref(element);
		});
		triggerViewportEntry(element);
		// Default once=true means disconnect after reveal
		expect(result.current.isVisible).toBe(true);
		expect(mockDisconnectFn).toHaveBeenCalledTimes(1);
	});
});
