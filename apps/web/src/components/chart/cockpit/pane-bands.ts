import type {
	Coordinate,
	IChartApiBase,
	IPanePrimitive,
	IPanePrimitivePaneView,
	IPrimitivePaneRenderer,
	PaneAttachedParameter,
	Time,
} from "lightweight-charts";

/**
 * 主图区间底色（如回撤 peak→trough 水下区间）：横向半透明色带。
 * 以 pane primitive 绘制，随时间轴缩放平移重算坐标，并出现在 PNG 截图中。
 */

type DrawTarget = Parameters<IPrimitivePaneRenderer["draw"]>[0];
type MediaScope = Parameters<Parameters<DrawTarget["useMediaCoordinateSpace"]>[0]>[0];

export type PaneBandRange = {
	readonly from: number;
	readonly to: number;
	/** CSS 颜色（已解析），按区间逐带指定。 */
	readonly fill: string;
};

export type PaneBandsOptions = {
	readonly ranges: readonly PaneBandRange[];
};

export class PaneBands implements IPanePrimitive<Time> {
	private options: PaneBandsOptions;
	private chart: IChartApiBase<Time> | null = null;
	private requestUpdate: (() => void) | null = null;
	private rects: Array<{ x1: Coordinate; x2: Coordinate; fill: string }> = [];
	private readonly view: IPanePrimitivePaneView;

	constructor(options: PaneBandsOptions) {
		this.options = options;
		this.view = {
			zOrder: () => "bottom",
			renderer: () => (this.rects.length > 0 ? this.renderer() : null),
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

	updateOptions(options: PaneBandsOptions): void {
		this.options = options;
		this.requestUpdate?.();
	}

	updateAllViews(): void {
		const timeScale = this.chart?.timeScale();
		if (!timeScale) {
			this.rects = [];
			return;
		}
		this.rects = this.options.ranges
			.map((range) => ({
				x1: timeScale.timeToCoordinate(range.from as Time),
				x2: timeScale.timeToCoordinate(range.to as Time),
				fill: range.fill,
			}))
			.filter((rect): rect is { x1: Coordinate; x2: Coordinate; fill: string } => rect.x1 !== null && rect.x2 !== null);
	}

	paneViews(): readonly IPanePrimitivePaneView[] {
		return [this.view];
	}

	private renderer(): IPrimitivePaneRenderer {
		const rects = this.rects;
		return {
			draw: (target: DrawTarget) => {
				target.useMediaCoordinateSpace((scope: MediaScope) => {
					const ctx = scope.context;
					const height = scope.mediaSize.height;
					ctx.save();
					for (const rect of rects) {
						ctx.fillStyle = rect.fill;
						ctx.fillRect(rect.x1, 0, rect.x2 - rect.x1, height);
					}
					ctx.restore();
				});
			},
		};
	}
}
