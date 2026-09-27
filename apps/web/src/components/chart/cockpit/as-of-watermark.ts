import type {
	IChartApiBase,
	IPanePrimitive,
	IPanePrimitivePaneView,
	IPrimitivePaneRenderer,
	Logical,
	PaneAttachedParameter,
	Time,
} from "lightweight-charts";

/**
 * as_of 水位线（本产品特有）：knowledge cutoff 竖线 + 顶部标签。
 * 以 pane primitive 绘制，随时间轴缩放平移自动重算坐标，并出现在 PNG 截图中。
 */

type DrawTarget = Parameters<IPrimitivePaneRenderer["draw"]>[0];
type MediaScope = Parameters<Parameters<DrawTarget["useMediaCoordinateSpace"]>[0]>[0];

export type AsOfWatermarkOptions = {
	readonly time: Time;
	readonly label: string;
	readonly lineColor: string;
	readonly labelColor: string;
};

/** 当日 UTC 0 点的 unix 秒；无法解析返回 null。 */
function utcDay(time: Time): number | null {
	if (typeof time === "number") return Math.floor(time / 86_400) * 86_400;
	if (typeof time === "string") {
		const parsed = Date.parse(`${time}T00:00:00Z`);
		return Number.isNaN(parsed) ? null : Math.floor(parsed / 1000 / 86_400) * 86_400;
	}
	if (typeof time === "object" && "year" in time) {
		return Math.floor(Date.UTC(time.year, (time.month ?? 1) - 1, time.day ?? 1) / 1000 / 86_400) * 86_400;
	}
	return null;
}

/** A 股会话时区（Asia/Shanghai，无夏令时）相对 UTC 的秒偏移。 */
const SESSION_UTC_OFFSET_SECONDS = 8 * 3_600;

/**
 * 交易所时区下的会话日（unix 秒）：会话日期是上海自然日，本地 00:00–08:00
 * 的 cutoff 在 UTC 下仍属前一日，必须按会话日比较才不会被归到最后一个
 * 已画会话上。Business-day 时间本身就是日期值，无需偏移。
 */
function sessionDay(time: Time): number | null {
	if (typeof time !== "number") return utcDay(time);
	return Math.floor((time + SESSION_UTC_OFFSET_SECONDS) / 86_400) * 86_400;
}

export class AsOfWatermark implements IPanePrimitive<Time> {
	private options: AsOfWatermarkOptions;
	private chart: IChartApiBase<Time> | null = null;
	private requestUpdate: (() => void) | null = null;
	private x: number | null = null;
	private edge: "left" | "right" | null = null;
	private readonly view: IPanePrimitivePaneView;

	constructor(options: AsOfWatermarkOptions) {
		this.options = options;
		this.view = {
			zOrder: () => "normal",
			renderer: () => (this.x === null && this.edge === null ? null : this.renderer()),
		};
	}

	attached(param: PaneAttachedParameter<Time>): void {
		this.chart = param.chart;
		this.requestUpdate = param.requestUpdate;
	}

	detached(): void {
		this.chart = null;
		this.requestUpdate = null;
	}

	updateOptions(options: AsOfWatermarkOptions): void {
		this.options = options;
		this.requestUpdate?.();
	}

	updateAllViews(): void {
		const scale = this.chart?.timeScale();
		this.x = scale?.timeToCoordinate(this.options.time) ?? null;
		this.edge = null;
		if (this.x === null && scale) {
			// Out-of-range cutoffs sit at the chart edge (spec 21: 水位线在
			// 图表右缘), never snapped onto a candle they postdate; nearest-
			// session snapping stays only for an intraday cutoff on the
			// plotted session at the range edge.
			const time = this.options.time;
			const day = sessionDay(time);
			const scaleWithRange = scale as { getVisibleRange?: () => { from: Time; to: Time } };
			const range = scaleWithRange.getVisibleRange?.() ?? null;
			const to = range ? sessionDay(range.to) : null;
			const from = range ? sessionDay(range.from) : null;
			const beyondRight = typeof time === "number" && range && time > (range.to as number) && day !== to;
			const beyondLeft = typeof time === "number" && range && time < (range.from as number) && day !== from;
			if (beyondRight) {
				this.edge = "right";
			} else if (beyondLeft) {
				this.edge = "left";
			} else {
				const index = scale.timeToIndex(time, true);
				this.x = index === null ? null : scale.logicalToCoordinate(Number(index) as Logical);
			}
		}
	}

	paneViews(): readonly IPanePrimitivePaneView[] {
		return [this.view];
	}

	private renderer(): IPrimitivePaneRenderer {
		const { lineColor, labelColor, label } = this.options;
		const edge = this.edge;
		const x = this.x;
		return {
			draw: (target: DrawTarget) => {
				target.useMediaCoordinateSpace((scope: MediaScope) => {
					const ctx = scope.context;
					const height = scope.mediaSize.height;
					const px = x ?? (edge === "right" ? scope.mediaSize.width - 1 : 1);
					ctx.save();
					ctx.strokeStyle = lineColor;
					ctx.lineWidth = 1;
					ctx.setLineDash([4, 3]);
					ctx.beginPath();
					ctx.moveTo(px, 0);
					ctx.lineTo(px, height);
					ctx.stroke();
					ctx.setLineDash([]);
					ctx.font = "10px sans-serif";
					const textWidth = ctx.measureText(label).width;
					ctx.fillStyle = labelColor;
					ctx.fillText(label, Math.max(2, Math.min(px + 3, scope.mediaSize.width - textWidth - 2)), 11);
					ctx.restore();
				});
			},
		};
	}
}
