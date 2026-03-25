import { renderHook, act } from "@testing-library/react";
import { describe, expect, it, beforeEach } from "vitest";
import { useTheme } from "../use-theme";

describe("useTheme", () => {
	beforeEach(() => {
		document.documentElement.classList.remove("dark", "light");
		localStorage.removeItem("ditto-theme");
	});

	it("默认为 dark 主题", () => {
		const { result } = renderHook(() => useTheme());
		expect(result.current.theme).toBe("dark");
		expect(document.documentElement.classList.contains("dark")).toBe(true);
	});

	it("切换到 light 主题", () => {
		const { result } = renderHook(() => useTheme());
		act(() => {
			result.current.setTheme("light");
		});
		expect(result.current.theme).toBe("light");
		expect(document.documentElement.classList.contains("light")).toBe(true);
		expect(document.documentElement.classList.contains("dark")).toBe(false);
	});

	it("切换回 dark 主题", () => {
		const { result } = renderHook(() => useTheme());
		act(() => {
			result.current.setTheme("light");
		});
		act(() => {
			result.current.setTheme("dark");
		});
		expect(result.current.theme).toBe("dark");
		expect(document.documentElement.classList.contains("dark")).toBe(true);
	});

	it("toggle 在 dark 和 light 之间切换", () => {
		const { result } = renderHook(() => useTheme());
		expect(result.current.theme).toBe("dark");

		act(() => {
			result.current.toggleTheme();
		});
		expect(result.current.theme).toBe("light");

		act(() => {
			result.current.toggleTheme();
		});
		expect(result.current.theme).toBe("dark");
	});
});
