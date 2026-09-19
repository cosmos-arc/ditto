import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {
	type Coordinate,
	createSeriesMarkers,
	type Logical,
	type LogicalRange,
	type MouseEventParams,
	type Time,
} from "lightweight-charts";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ChartCockpit, type CockpitSeriesSpec } from "./chart-cockpit";
import { broadcastCrosshairTime, joinRangeGroup } from "./cockpit-link";

/**
 * lightweight-charts 依赖 canvas 2D，jsdom 无法承载；这里 mock 引擎，
 * 只断言组件对引擎喂养的数据映射与 DOM 交互合同（外部行为），
 * 不测图表库内部实现。
 */

const hoisted = vi.hoisted(() => ({
	setSeriesMarkers: vi.fn<(markers: unknown[]) => void>(),
}));
const seriesDataCalls: unknown[][] = [];
const setVisibleLogicalRange = vi.fn<(range: LogicalRange) => void>();
const fitContent = vi.fn<() => void>();
const attachPrimitive = vi.fn<(primitive: object) => void>();
// vi.mock 工厂被提升到 const 声明之前，marker 捕获必须经 vi.hoisted 暴露。
let crosshairHandlers: Array<(param: MouseEventParams<Time>) => void> = [];
let clickHandlers: Array<(param: MouseEventParams<Time>) => void> = [];
let logicalRangeHandlers: Array<(range: LogicalRange | null) => void> = [];
const timeScaleStub = {
	getVisibleLogicalRange: vi.fn<() => LogicalRange | null>(() => ({ from: 0 as Logical, to: 100 as Logical })),
	setVisibleLogicalRange,
	coordinateToLogical: vi.fn((x: number) => x as Logical),
	timeToCoordinate: vi.fn<(time: Time) => number | null>(() => 42),
	fitContent,
	subscribeVisibleLogicalRangeChange: vi.fn((handler: (range: LogicalRange | null) => void) => {
		logicalRangeHandlers.push(handler);
	}),
};

const chartStub = {
	addSeries: vi.fn((_definition: unknown, _options: unknown, _paneIndex?: number) => {
		return {
			setData: vi.fn((data: unknown[]) => {
				seriesDataCalls.push(data);
			}),
			remove: vi.fn(),
		};
	}),
	removeSeries: vi.fn(),
	panes: vi.fn(() => [
		{ attachPrimitive, setHeight: vi.fn() },
		{ attachPrimitive, setHeight: vi.fn() },
	]),
	subscribeCrosshairMove: vi.fn((handler: (param: MouseEventParams<Time>) => void) => {
		crosshairHandlers.push(handler);
	}),
	subscribeClick: vi.fn((handler: (param: MouseEventParams<Time>) => void) => {
		clickHandlers.push(handler);
	}),
	subscribeVisibleLogicalRangeChange: vi.fn((handler: (range: LogicalRange | null) => void) => {
		logicalRangeHandlers.push(handler);
	}),
	setCrosshairPosition: vi.fn(),
	clearCrosshairPosition: vi.fn(),
	takeScreenshot: vi.fn(() => ({ width: 100, height: 50 })),
	applyOptions: vi.fn(),
	remove: vi.fn(),
	timeScale: vi.fn(() => timeScaleStub),
};

vi.mock("lightweight-charts", async (importOriginal) => {
	const actual = await importOriginal<typeof import("lightweight-charts")>();
	return {
		...actual,
		createChart: vi.fn(() => chartStub),
		createSeriesMarkers: vi.fn(() => ({ setMarkers: hoisted.setSeriesMarkers })),
	};
});

const BARS: CockpitSeriesSpec["bars"] = [
	{ time: 100, close: 10, volume: 100 },
	{ time: 200, close: null, volume: null },
	{ time: 300, close: 12, volume: 120 },
];

const SERIES: CockpitSeriesSpec[] = [{ id: "close", bars: BARS, color: "var(--chart-run-1)" }];

function renderCockpit(overrides: Record<string, unknown> = {}) {
	return render(
		<ChartCockpit
			chartId="spec-close"
			rangeId="spec-range"
			ariaLabel="演示收盘价图表（fixture）"
			series={SERIES}
			identity={{ dataSourceName: "fixture", snapshotId: "snap-full-id" }}
			{...overrides}
		/>,
	);
}

const originalCreateObjectURL = URL.createObjectURL;
const originalRevokeObjectURL = URL.revokeObjectURL;

beforeEach(() => {
	vi.clearAllMocks();
	crosshairHandlers = [];
	clickHandlers = [];
	logicalRangeHandlers = [];
	seriesDataCalls.length = 0;
	URL.createObjectURL = vi.fn(() => "blob:mock");
	URL.revokeObjectURL = vi.fn();
});

afterEach(() => {
	cleanup();
	URL.createObjectURL = originalCreateObjectURL;
	URL.revokeObjectURL = originalRevokeObjectURL;
});

describe("ChartCockpit DOM 合同", () => {
	it("exposes chart interaction contract attributes and focusability", () => {
		renderCockpit();
		const host = screen.getByLabelText("演示收盘价图表（fixture）");
		expect(host).toHaveAttribute("data-chart-interaction-contract", "spec-close");
		expect(host).toHaveAttribute("data-chart-affordances", "crosshair tooltip zoom-pan linked-time-range");
		expect(host).toHaveAttribute("data-chart-linked-time-range", "spec-range");
		expect(host).toHaveAttribute("tabindex", "0");
	});

	it("marks the as_of watermark on the host element", () => {
		renderCockpit({ asOf: { time: 250 } });
		expect(screen.getByLabelText("演示收盘价图表（fixture）")).toHaveAttribute("data-chart-as-of", "250");
	});

	it("attaches the as_of watermark primitive to the price pane", () => {
		renderCockpit({ asOf: { time: 250 } });
		expect(attachPrimitive).toHaveBeenCalled();
	});
});

describe("ChartCockpit 数据映射", () => {
	it("feeds the engine whitespace points at missing closes so gaps are not interpolated", () => {
		renderCockpit();
		const flat = seriesDataCalls.flat();
		expect(flat).toContainEqual({ time: 200 });
		expect(flat).toContainEqual({ time: 100, value: 10 });
		expect(flat).toContainEqual({ time: 300, value: 12 });
	});

	it("splits freshness-faded series into one engine series per bucket run", () => {
		// ages at nowMs=400s：t100→300s（stale 边界）、t200/t300→aging
		renderCockpit({ freshnessFade: true, nowMs: 400 * 1000 });
		expect(chartStub.addSeries).toHaveBeenCalledTimes(2);
		// 第二段（aging）以前段最后一点为连接点，折线不断开。
		expect(seriesDataCalls[1]).toEqual([{ time: 100, value: 10 }, { time: 200 }, { time: 300, value: 12 }]);
	});

	it("renders each freshness run at its bucket alpha from the token ramp", () => {
		// ages at nowMs=1h：全部 expired（0.25）；base 色走 fallback 涨色 → #eb6268
		renderCockpit({
			freshnessFade: true,
			nowMs: 3_600 * 1000,
			series: [{ id: "close", bars: BARS, color: "var(--chart-series-up)" }],
		});
		expect(chartStub.addSeries).toHaveBeenCalledWith(
			expect.anything(),
			expect.objectContaining({ color: "rgba(235, 98, 104, 0.25)" }),
			0,
		);
	});

	it("renders overlays on pane 0 and sub-panes after the volume pane", () => {
		renderCockpit({
			showVolumePane: true,
			overlays: [
				{
					id: "ma_5",
					color: "var(--chart-run-1)",
					points: [
						{ time: 100, close: 10, volume: null },
						{ time: 200, close: null, volume: null },
					],
				},
			],
			subPanes: [
				{
					id: "rsi",
					label: "RSI(14)",
					series: [
						{
							id: "rsi",
							color: "var(--chart-run-4)",
							points: [
								{ time: 100, close: 55, volume: null },
								{ time: 200, close: null, volume: null },
							],
						},
					],
				},
				{
					id: "macd",
					label: "MACD(12,26,9)",
					series: [
						{
							id: "macd_histogram",
							color: "var(--chart-series-neutral)",
							kind: "histogram",
							points: [{ time: 100, close: 0.4, volume: null }],
						},
					],
				},
			],
		});
		// 主蜡烛(1) + overlay(1) + 量(1) + RSI 线(1) + MACD 柱(1) = 5 个引擎序列
		expect(chartStub.addSeries).toHaveBeenCalledTimes(5);
		const paneIndexes = chartStub.addSeries.mock.calls.map((call) => call[2]);
		expect(paneIndexes).toEqual([0, 0, 1, 2, 3]);
		expect(screen.getByLabelText("演示收盘价图表（fixture）")).toHaveAttribute("data-chart-panes", "4");
	});

	it("renders candle specs through the candle series with market up/down colors", () => {
		renderCockpit({
			series: [
				{
					id: "daily",
					kind: "candle",
					color: "var(--chart-combo-model)",
					bars: [
						{ time: 100, open: 10, high: 11, low: 9, close: 10.5, volume: 100 },
						{ time: 200, close: null, volume: null },
					],
				},
			],
		});
		expect(chartStub.addSeries).toHaveBeenCalledWith(
			expect.anything(),
			expect.objectContaining({ upColor: "#eb6268", downColor: "#53ae77" }),
			0,
		);
		expect(seriesDataCalls[0]).toEqual([{ time: 100, open: 10, high: 11, low: 9, close: 10.5 }, { time: 200 }]);
	});
});

describe("ChartCockpit 键盘操作", () => {
	it("pans with arrows, zooms with +/-, jumps to the tail with End, resets on dblclick", async () => {
		renderCockpit();
		const user = userEvent.setup();
		const host = screen.getByLabelText("演示收盘价图表（fixture）");
		await user.click(host);
		// 引擎 stub 的可见区间恒为 {0,100}，断言各按键基于该区间的计算结果。
		await user.keyboard("{ArrowRight}");
		expect(setVisibleLogicalRange).toHaveBeenLastCalledWith({ from: 10, to: 110 });
		await user.keyboard("{Shift>}{ArrowLeft}{/Shift}");
		expect(setVisibleLogicalRange).toHaveBeenLastCalledWith({ from: -25, to: 75 });
		await user.keyboard("{ArrowUp}");
		expect(setVisibleLogicalRange).toHaveBeenLastCalledWith({ from: -10, to: 90 });
		await user.keyboard("+");
		expect(setVisibleLogicalRange).toHaveBeenLastCalledWith({ from: 10, to: 90 });
		await user.keyboard("-");
		expect(setVisibleLogicalRange).toHaveBeenLastCalledWith({ from: -12.5, to: 112.5 });
		await user.keyboard("{End}");
		expect(setVisibleLogicalRange).toHaveBeenLastCalledWith({ from: -96, to: 4 });
		await user.keyboard("{Home}");
		expect(setVisibleLogicalRange).toHaveBeenLastCalledWith({ from: -1, to: 99 });
		await user.dblClick(host);
		expect(fitContent).toHaveBeenCalled();
	});

	it("zooms to a shift-drag box selection and ignores tiny selections", () => {
		renderCockpit();
		const host = screen.getByLabelText("演示收盘价图表（fixture）");
		fireEvent.mouseDown(host, { shiftKey: true, button: 0, clientX: 10, clientY: 5 });
		fireEvent.mouseMove(host, { clientX: 60, clientY: 5 });
		expect(screen.getByTestId("chart-selection-spec-close")).toBeInTheDocument();
		fireEvent.mouseUp(host, { clientX: 60, clientY: 5 });
		expect(screen.queryByTestId("chart-selection-spec-close")).not.toBeInTheDocument();
		expect(setVisibleLogicalRange).toHaveBeenLastCalledWith({ from: 10, to: 60 });

		fireEvent.mouseDown(host, { shiftKey: true, button: 0, clientX: 10, clientY: 5 });
		fireEvent.mouseUp(host, { clientX: 14, clientY: 5 });
		expect(setVisibleLogicalRange).toHaveBeenCalledTimes(1);
	});
});

describe("ChartCockpit 缺口标注", () => {
	it("labels the first missing range in the header", () => {
		renderCockpit();
		const chip = screen.getByTestId("chart-gaps-spec-close");
		expect(chip.textContent).toContain("缺口");
		expect(chip.textContent).toContain("1970-01-01 00:03");
	});
});

describe("ChartCockpit 读数口径与副图图例", () => {
	it("formats main-series readout through the per-series formatter", () => {
		renderCockpit({
			series: [{ ...SERIES[0]!, id: "nav", format: (value: number) => value.toFixed(4) }],
		});
		// 默认读数锚定最后一个非空点（t=300, close=12）
		expect(screen.getByTestId("chart-readout-spec-close-nav").textContent).toBe("12.0000");
	});

	it("renders sub-pane readout chips with labels and formatters, gaps as —", () => {
		renderCockpit({
			subPanes: [
				{
					id: "excess",
					label: "超额收益",
					series: [
						{
							id: "excess",
							label: "超额",
							color: "var(--chart-run-2)",
							format: (value: number) => `${value > 0 ? "+" : ""}${(value * 100).toFixed(2)}%`,
							points: [
								{ time: 100, close: 0.012, volume: null },
								{ time: 200, close: null, volume: null },
								{ time: 300, close: -0.005, volume: null },
							],
						},
					],
				},
			],
		});
		// 默认读数锚定主序列最后非空点 t=300 → 副图同时点取值
		expect(screen.getByTestId("chart-readout-spec-close-excess").textContent).toBe("-0.50%");
		expect(screen.getByText("超额")).toBeInTheDocument();
	});

	it("keeps the readout index O(1): crosshair moves resolve values without rescanning", () => {
		renderCockpit({
			subPanes: [
				{
					id: "dd",
					label: "回撤",
					series: [
						{
							id: "dd",
							color: "var(--chart-series-down)",
							points: [
								{ time: 100, close: -1, volume: null },
								{ time: 300, close: -3, volume: null },
							],
						},
					],
				},
			],
		});
		act(() => {
			for (const handler of crosshairHandlers) {
				handler({
					time: 300 as Time,
					point: { x: 10 as Coordinate, y: 10 as Coordinate },
					seriesData: new Map(),
				});
			}
		});
		expect(screen.getByTestId("chart-readout-spec-close-dd").textContent).toBe("-3");
		act(() => {
			for (const handler of crosshairHandlers) {
				handler({ seriesData: new Map() });
			}
		});
		// 离开图表后回落到最后非空点读数
		expect(screen.getByTestId("chart-readout-spec-close-dd").textContent).toBe("-3");
	});
});

describe("ChartCockpit 主图区间底色", () => {
	it("attaches the bands primitive and feeds resolved token ranges", () => {
		renderCockpit({
			bands: [{ id: "dd-1", from: 100, to: 300, color: "var(--chart-series-down)" }],
		});
		// 主图 pane 挂载水位线 + 底色两个 primitive
		expect(attachPrimitive).toHaveBeenCalledTimes(2);
	});
});

describe("Chart Cockpit 跨实例联动", () => {
	it("broadcasts visible range to other members of the same range group", () => {
		renderCockpit();
		const applied: LogicalRange[] = [];
		const leave = joinRangeGroup("spec-range", {
			id: "peer",
			applyVisibleRange: (range) => applied.push(range),
			onLinkedCrosshair: () => undefined,
		});
		act(() => {
			for (const handler of logicalRangeHandlers) {
				handler({ from: 5 as Logical, to: 50 as Logical });
			}
		});
		expect(applied).toEqual([{ from: 5, to: 50 }]);
		expect(screen.getByLabelText("演示收盘价图表（fixture）")).toHaveAttribute("data-chart-visible-range", "5.0,50.0");
		leave();
	});

	it("syncs a linked crosshair timestamp onto its own primary series", () => {
		renderCockpit();
		const leave = joinRangeGroup("spec-range", {
			id: "peer",
			applyVisibleRange: () => undefined,
			onLinkedCrosshair: () => undefined,
		});
		// 模拟同组另一成员广播十字线时间戳：本 cockpit 应把该时点的值画上自己的十字线。
		act(() => {
			broadcastCrosshairTime("spec-range", "peer", 300 as Time);
		});
		expect(chartStub.setCrosshairPosition).toHaveBeenCalledWith(12, 300, expect.anything());
		leave();
	});
});

describe("ChartCockpit 买卖点标记与下钻定位", () => {
	it("maps buy markers to above-bar arrows and sell to below-bar arrows with market colors", () => {
		renderCockpit({
			markers: [
				{ id: "t1", time: 100, direction: "buy", label: "买入" },
				{ id: "t2", time: 300, direction: "sell", label: "卖出" },
			],
		});
		expect(vi.mocked(createSeriesMarkers)).toHaveBeenCalledWith(expect.anything(), [
			expect.objectContaining({ time: 100, position: "aboveBar", shape: "arrowUp", text: "买入" }),
			expect.objectContaining({ time: 300, position: "belowBar", shape: "arrowDown", text: "卖出" }),
		]);
		const host = screen.getByLabelText("演示收盘价图表（fixture）");
		expect(host).toHaveAttribute("data-chart-marker-times", "100,300");
	});

	it("invokes onMarkerClick only when the clicked time hits a marker", () => {
		const onMarkerClick = vi.fn();
		renderCockpit({
			markers: [{ id: "t1", time: 300, direction: "sell" }],
			onMarkerClick,
		});
		act(() => {
			for (const handler of clickHandlers) {
				handler({
					time: 300 as Time,
					point: { x: 5 as Coordinate, y: 5 as Coordinate },
					seriesData: new Map(),
				});
			}
		});
		expect(onMarkerClick).toHaveBeenCalledWith(expect.objectContaining({ id: "t1", direction: "sell" }));
		act(() => {
			for (const handler of clickHandlers) {
				handler({ time: 100 as Time, point: { x: 5 as Coordinate, y: 5 as Coordinate }, seriesData: new Map() });
			}
		});
		expect(onMarkerClick).toHaveBeenCalledTimes(1);
	});

	it("scrolls the initial focus time into the visible center instead of fitContent", () => {
		renderCockpit({ initialFocusTime: 200 });
		// t=200 是第 2 根 bar（index 1）；fixture 仅 3 根 → 可见窗口=序列长度，目标居中
		expect(setVisibleLogicalRange).toHaveBeenLastCalledWith({ from: -0.5, to: 2.5 });
		expect(fitContent).not.toHaveBeenCalled();
	});

	it("falls back to fitContent when the focus time is not in the series", () => {
		renderCockpit({ initialFocusTime: 999 });
		expect(fitContent).toHaveBeenCalled();
	});
});

describe("ChartCockpit 导出", () => {
	it("exports CSV with PIT identity columns via download", async () => {
		renderCockpit({ asOf: { time: 250 } });
		const user = userEvent.setup();
		await user.click(screen.getByTestId("chart-export-csv-spec-close"));
		expect(URL.createObjectURL).toHaveBeenCalledTimes(1);
		const blob = vi.mocked(URL.createObjectURL).mock.calls[0]?.[0] as Blob;
		const text = await blob.text();
		expect(text.split("\n")[0]).toBe(
			"time,close_close,volume,as_of,snapshot_id,knowledge_cutoff,publication_cutoff,data_source,exported_at,product_version",
		);
		expect(text).toContain("snap-full-id");
		expect(URL.revokeObjectURL).toHaveBeenCalled();
	});

	it("exports PNG composed from the screenshot with a footer band", async () => {
		const contextStub = {
			fillStyle: "",
			font: "",
			fillRect: vi.fn(),
			drawImage: vi.fn(),
			fillText: vi.fn(),
		};
		const toBlob = vi.fn((callback: (blob: Blob | null) => void) => {
			callback(new Blob(["png"], { type: "image/png" }));
		});
		const createElement = document.createElement.bind(document);
		vi.spyOn(document, "createElement").mockImplementation((tagName: string) => {
			const element = createElement(tagName);
			if (tagName === "canvas") {
				const canvas = element as HTMLCanvasElement;
				canvas.getContext = (() => contextStub) as unknown as HTMLCanvasElement["getContext"];
				canvas.toBlob = toBlob;
			}
			return element;
		});
		try {
			renderCockpit({ asOf: { time: 250 } });
			const user = userEvent.setup();
			await user.click(screen.getByTestId("chart-export-png-spec-close"));
			expect(toBlob).toHaveBeenCalledTimes(1);
			// footer 两行 PIT 溯源文本绘制在截图下方
			expect(contextStub.fillText).toHaveBeenCalledTimes(2);
			expect(contextStub.fillRect).toHaveBeenCalled();
			expect(URL.createObjectURL).toHaveBeenCalledTimes(1);
		} finally {
			vi.mocked(document.createElement).mockRestore();
		}
	});
});
