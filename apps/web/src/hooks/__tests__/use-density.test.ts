import { renderHook, act } from "@testing-library/react";
import { describe, expect, it, beforeEach } from "vitest";
import { useDensity } from "../use-density";

describe("useDensity", () => {
	beforeEach(() => {
		document.documentElement.removeAttribute("data-grid-density");
		localStorage.removeItem("ditto-density");
	});

	it("默认为 compact 密度", () => {
		const { result } = renderHook(() => useDensity());
		expect(result.current.density).toBe("compact");
		expect(
			document.documentElement.getAttribute("data-grid-density"),
		).toBe("compact");
	});

	it("切换到 comfortable 密度", () => {
		const { result } = renderHook(() => useDensity());
		act(() => {
			result.current.setDensity("comfortable");
		});
		expect(result.current.density).toBe("comfortable");
		expect(
			document.documentElement.getAttribute("data-grid-density"),
		).toBe("comfortable");
	});

	it("切换到 ultra-compact 密度", () => {
		const { result } = renderHook(() => useDensity());
		act(() => {
			result.current.setDensity("ultra-compact");
		});
		expect(result.current.density).toBe("ultra-compact");
		expect(
			document.documentElement.getAttribute("data-grid-density"),
		).toBe("ultra-compact");
	});

	it("三种密度循环切换", () => {
		const { result } = renderHook(() => useDensity());
		expect(result.current.density).toBe("compact");

		act(() => {
			result.current.cycleDensity();
		});
		expect(result.current.density).toBe("comfortable");

		act(() => {
			result.current.cycleDensity();
		});
		expect(result.current.density).toBe("ultra-compact");

		act(() => {
			result.current.cycleDensity();
		});
		expect(result.current.density).toBe("compact");
	});
});
