import { describe, it, expect, vi } from "vitest";
import { renderHook } from "@testing-library/react";
import { useMouseGlow } from "./use-mouse-glow";

describe("useMouseGlow", () => {
	it("returns a ref and handlers object", () => {
		const { result } = renderHook(() => useMouseGlow());
		const [ref, handlers] = result.current;

		expect(ref).toBeDefined();
		expect(ref.current).toBeNull();
		expect(handlers).toHaveProperty("onMouseMove");
		expect(handlers).toHaveProperty("onMouseLeave");
		expect(typeof handlers.onMouseMove).toBe("function");
		expect(typeof handlers.onMouseLeave).toBe("function");
	});

	it("sets --_glow-x and --_glow-y on mouseMove", () => {
		const { result } = renderHook(() => useMouseGlow());
		const [ref, handlers] = result.current;

		const element = document.createElement("div");
		// getBoundingClientRect mock
		element.getBoundingClientRect = vi.fn(() => ({
			left: 100,
			top: 50,
			right: 500,
			bottom: 350,
			width: 400,
			height: 300,
			x: 100,
			y: 50,
			toJSON: () => ({}),
		}));
		ref.current = element;

		handlers.onMouseMove({
			currentTarget: element,
			clientX: 200,
			clientY: 150,
		} as React.MouseEvent<HTMLElement>);

		expect(element.style.getPropertyValue("--_glow-x")).toBe("100px");
		expect(element.style.getPropertyValue("--_glow-y")).toBe("100px");
	});

	it("resets CSS variables on mouseLeave", () => {
		const { result } = renderHook(() => useMouseGlow());
		const [ref, handlers] = result.current;

		const element = document.createElement("div");
		element.getBoundingClientRect = vi.fn(() => ({
			left: 100,
			top: 50,
			right: 500,
			bottom: 350,
			width: 400,
			height: 300,
			x: 100,
			y: 50,
			toJSON: () => ({}),
		}));
		ref.current = element;

		// First set values
		handlers.onMouseMove({
			currentTarget: element,
			clientX: 200,
			clientY: 150,
		} as React.MouseEvent<HTMLElement>);

		expect(element.style.getPropertyValue("--_glow-x")).toBe("100px");

		// Then leave
		handlers.onMouseLeave();

		expect(element.style.getPropertyValue("--_glow-x")).toBe("");
		expect(element.style.getPropertyValue("--_glow-y")).toBe("");
	});

	it("calculates position relative to element bounds", () => {
		const { result } = renderHook(() => useMouseGlow());
		const [ref, handlers] = result.current;

		const element = document.createElement("div");
		element.getBoundingClientRect = vi.fn(() => ({
			left: 0,
			top: 0,
			right: 800,
			bottom: 600,
			width: 800,
			height: 600,
			x: 0,
			y: 0,
			toJSON: () => ({}),
		}));
		ref.current = element;

		handlers.onMouseMove({
			currentTarget: element,
			clientX: 400,
			clientY: 300,
		} as React.MouseEvent<HTMLElement>);

		expect(element.style.getPropertyValue("--_glow-x")).toBe("400px");
		expect(element.style.getPropertyValue("--_glow-y")).toBe("300px");
	});

	it("handlers are stable across rerenders (useCallback)", () => {
		const { result, rerender } = renderHook(() => useMouseGlow());
		const [, handlersA] = result.current;

		rerender();
		const [, handlersB] = result.current;

		expect(handlersA.onMouseMove).toBe(handlersB.onMouseMove);
		expect(handlersA.onMouseLeave).toBe(handlersB.onMouseLeave);
	});
});
