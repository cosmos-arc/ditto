import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { LineChart } from "./line-chart";
import { AreaChart } from "./area-chart";
import type { SparklinePoint } from "@/types";

const mockData: SparklinePoint[] = [
	{ time: "2026-04-01", value: 100 },
	{ time: "2026-04-02", value: 102 },
	{ time: "2026-04-03", value: 98 },
	{ time: "2026-04-04", value: 105 },
	{ time: "2026-04-05", value: 103 },
];

/**
 * Recharts 的 ResponsiveContainer 在 jsdom 中无法获取容器尺寸。
 * 通过 mock ResizeObserver 提供固定尺寸来解决这个问题。
 */
function mockResizeObserver(): () => void {
	const observer = class {
		readonly callback: ResizeObserverCallback;
		constructor(callback: ResizeObserverCallback) {
			this.callback = callback;
		}
		observe() {
			this.callback(
				[{ contentRect: { width: 400, height: 200 } }] as ResizeObserverEntry[],
				this,
			);
		}
		unobserve() {}
		disconnect() {}
	};
	globalThis.ResizeObserver = observer as unknown as typeof ResizeObserver;
	return () => {
		delete globalThis.ResizeObserver;
	};
}

describe("LineChart", () => {
	let cleanup: () => void;

	beforeEach(() => {
		cleanup = mockResizeObserver();
	});

	afterEach(() => {
		cleanup();
	});

	it("渲染 SVG 容器", () => {
		const { container } = render(
			<LineChart data={mockData} height={200} />,
		);
		const svg = container.querySelector("svg");
		expect(svg).toBeInTheDocument();
	});

	it("显示正确的数据点数量", () => {
		const { container } = render(
			<LineChart data={mockData} height={200} />,
		);
		const circles = container.querySelectorAll("circle");
		expect(circles.length).toBe(mockData.length);
	});

	it("空数据时不崩溃", () => {
		const { container } = render(
			<LineChart data={[]} height={200} />,
		);
		const svg = container.querySelector("svg");
		expect(svg).toBeInTheDocument();
	});

	it("应用自定义 className", () => {
		const { container } = render(
			<LineChart data={mockData} height={200} className="my-chart" />,
		);
		const wrapper = container.firstChild as HTMLElement;
		expect(wrapper.classList.contains("my-chart")).toBe(true);
	});
});

describe("AreaChart", () => {
	let cleanup: () => void;

	beforeEach(() => {
		cleanup = mockResizeObserver();
	});

	afterEach(() => {
		cleanup();
	});

	it("渲染 SVG 容器", () => {
		const { container } = render(
			<AreaChart data={mockData} height={200} />,
		);
		const svg = container.querySelector("svg");
		expect(svg).toBeInTheDocument();
	});

	it("渲染 path 元素（面积区域）", () => {
		const { container } = render(
			<AreaChart data={mockData} height={200} />,
		);
		const paths = container.querySelectorAll("path");
		expect(paths.length).toBeGreaterThan(0);
	});
});
