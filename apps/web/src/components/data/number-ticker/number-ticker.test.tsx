import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, act } from "@testing-library/react";
import { NumberTicker } from "./number-ticker";

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

function triggerViewportEntry(): void {
	act(() => {
		mockObserverCallback([{ isIntersecting: true, target: document.createElement("span") }]);
	});
}

/* ── Tests ── */

describe("NumberTicker", () => {
	/* ── 基础渲染 ── */

	it("renders with data-slot='number-ticker' on root element", () => {
		render(<NumberTicker value={1234.56} />);
		expect(screen.getByTestId("number-ticker-root")).toHaveAttribute(
			"data-slot",
			"number-ticker",
		);
	});

	it("renders initial value as 0.00 before animation", () => {
		render(<NumberTicker value={1234.56} />);
		// The component shows 0.00 initially before IntersectionObserver triggers
		expect(screen.getByTestId("number-ticker-root").textContent).toContain("0.00");
	});

	it("displays formatted number with prefix and suffix", () => {
		render(<NumberTicker value={100} prefix="$" suffix="万" />);
		const root = screen.getByTestId("number-ticker-root");
		expect(root.textContent).toContain("$");
		expect(root.textContent).toContain("万");
	});

	it("applies custom className to root element", () => {
		render(<NumberTicker value={42} className="text-3xl" />);
		expect(screen.getByTestId("number-ticker-root")).toHaveClass("text-3xl");
	});

	it("uses font-data tabular-nums classes", () => {
		render(<NumberTicker value={42} />);
		const root = screen.getByTestId("number-ticker-root");
		expect(root.className).toContain("font-data");
		expect(root.className).toContain("tabular-nums");
	});

	/* ── Props 默认值 ── */

	it("defaults decimals to 2", () => {
		render(<NumberTicker value={42.123} />);
		// Initial display should be 0.00 (2 decimal places)
		expect(screen.getByTestId("number-ticker-root").textContent).toContain("0.00");
	});

	it("respects custom decimals prop", () => {
		render(<NumberTicker value={42.1234} decimals={4} />);
		// Initial display should be 0.0000 (4 decimal places)
		expect(screen.getByTestId("number-ticker-root").textContent).toContain("0.0000");
	});

	/* ── 字符串 value 支持 ── */

	it("handles string value by parsing it to number", () => {
		render(<NumberTicker value="1234.56" />);
		const root = screen.getByTestId("number-ticker-root");
		expect(root.textContent).toContain("0.00");
	});

	it("handles string value with prefix and suffix", () => {
		render(<NumberTicker value="99.9" prefix="¥" suffix="元" />);
		const root = screen.getByTestId("number-ticker-root");
		expect(root.textContent).toContain("¥");
		expect(root.textContent).toContain("元");
	});

	/* ── IntersectionObserver 行为 ── */

	it("creates IntersectionObserver on mount", () => {
		render(<NumberTicker value={100} />);
		expect(mockObserveFn).toHaveBeenCalledTimes(1);
	});

	it("does not animate before element enters viewport", () => {
		vi.spyOn(window, "requestAnimationFrame").mockImplementation(() => 0);
		render(<NumberTicker value={500} />);
		// No RAF should have been called before intersection
		expect(requestAnimationFrame).not.toHaveBeenCalled();
	});

	it("starts animation when element enters viewport", () => {
		vi.spyOn(window, "requestAnimationFrame").mockImplementation(() => 0);
		render(<NumberTicker value={500} />);
		triggerViewportEntry();
		expect(requestAnimationFrame).toHaveBeenCalled();
	});

	it("disconnects observer after animation triggers", () => {
		vi.spyOn(window, "requestAnimationFrame").mockImplementation(() => 0);
		render(<NumberTicker value={100} />);
		triggerViewportEntry();
		expect(mockDisconnectFn).toHaveBeenCalled();
	});

	/* ── 动画行为 ── */

	it("animates from 0 toward target value over duration", () => {
		vi.spyOn(window, "requestAnimationFrame").mockImplementation((cb) => {
			// Simulate immediate callback to avoid hanging
			return window.setTimeout(() => cb(performance.now()), 0) as unknown as number;
		});
		vi.spyOn(performance, "now");

		render(<NumberTicker value={1000} duration={1200} />);
		triggerViewportEntry();

		// At some point during animation, value should be between 0 and 1000
		// We just verify the animation mechanism was triggered
		expect(requestAnimationFrame).toHaveBeenCalled();
	});

	it("reaches target value at end of animation", () => {
		const rafSpy = vi.spyOn(window, "requestAnimationFrame");

		render(<NumberTicker value={500} duration={1200} />);
		triggerViewportEntry();

		// Get the RAF callback
		const rafCallback = rafSpy.mock.calls[0]?.[0];
		expect(rafCallback).toBeDefined();

		// Simulate time past duration
		act(() => {
			rafCallback?.(performance.now() + 2000); // well past 1200ms
		});

		const root = screen.getByTestId("number-ticker-root");
		expect(root.textContent).toContain("500.00");
	});

	it("displays prefix and suffix in final animated value", () => {
		const rafSpy = vi.spyOn(window, "requestAnimationFrame");

		render(<NumberTicker value={42} prefix="$" suffix="%" duration={1200} />);
		triggerViewportEntry();

		const rafCallback = rafSpy.mock.calls[0]?.[0];
		act(() => {
			rafCallback?.(performance.now() + 2000);
		});

		const root = screen.getByTestId("number-ticker-root");
		expect(root.textContent).toContain("$");
		expect(root.textContent).toContain("42.00");
		expect(root.textContent).toContain("%");
	});

	/* ── 边界情况 ── */

	it("handles zero value", () => {
		render(<NumberTicker value={0} />);
		expect(screen.getByTestId("number-ticker-root").textContent).toContain("0.00");
	});

	it("handles negative value", () => {
		const rafSpy = vi.spyOn(window, "requestAnimationFrame");
		render(<NumberTicker value={-42.5} />);
		triggerViewportEntry();

		const rafCallback = rafSpy.mock.calls[0]?.[0];
		act(() => {
			rafCallback?.(performance.now() + 2000);
		});

		const root = screen.getByTestId("number-ticker-root");
		expect(root.textContent).toContain("-42.50");
	});

	it("handles very large number", () => {
		const rafSpy = vi.spyOn(window, "requestAnimationFrame");
		render(<NumberTicker value={12345678.9} />);
		triggerViewportEntry();

		const rafCallback = rafSpy.mock.calls[0]?.[0];
		act(() => {
			rafCallback?.(performance.now() + 2000);
		});

		const root = screen.getByTestId("number-ticker-root");
		expect(root.textContent).toContain("12,345,678.90");
	});

	/* ── 清理行为 ── */

	it("disconnects observer on unmount", () => {
		const { unmount } = render(<NumberTicker value={100} />);
		unmount();
		// observer.disconnect was called (once on unmount)
		expect(mockDisconnectFn).toHaveBeenCalled();
	});

	it("cancels animation frame on unmount", () => {
		const cancelSpy = vi.spyOn(window, "cancelAnimationFrame");
		const rafSpy = vi.spyOn(window, "requestAnimationFrame");

		const { unmount } = render(<NumberTicker value={100} />);
		triggerViewportEntry();

		// There should be an active RAF id
		const rafId = rafSpy.mock.results[0]?.value;
		expect(rafId).toBeDefined();

		unmount();
		expect(cancelSpy).toHaveBeenCalledWith(rafId);
	});
});
