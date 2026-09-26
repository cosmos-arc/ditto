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

export class AsOfWatermark implements IPanePrimitive<Time> {
	private options: AsOfWatermarkOptions;
	private chart: IChartApiBase<Time> | null = null;
	private requestUpdate: (() => void) | null = null;
	private x: number | null = null;
	private readonly view: IPanePrimitivePaneView;

	constructor(options: AsOfWatermarkOptions) {
		this.options = options;
		this.view = {
			zOrder: () => "normal",
			renderer: () => (this.x === null ? null : this.renderer()),
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
		if (this.x === null && scale) {
			const index = scale.timeToIndex(this.options.time, true);
			this.x = index === null ? null : scale.logicalToCoordinate(Number(index) as Logical);
		}
	}

	paneViews(): readonly IPanePrimitivePaneView[] {
		return [this.view];
	}

	private renderer(): IPrimitivePaneRenderer {
		const { lineColor, labelColor, label } = this.options;
		const x = this.x ?? 0;
		return {
			draw: (target: DrawTarget) => {
				target.useMediaCoordinateSpace((scope: MediaScope) => {
					const ctx = scope.context;
					const height = scope.mediaSize.height;
					ctx.save();
					ctx.strokeStyle = lineColor;
					ctx.lineWidth = 1;
					ctx.setLineDash([4, 3]);
					ctx.beginPath();
					ctx.moveTo(x, 0);
					ctx.lineTo(x, height);
					ctx.stroke();
					ctx.setLineDash([]);
					ctx.font = "10px sans-serif";
					const textWidth = ctx.measureText(label).width;
					ctx.fillStyle = labelColor;
					ctx.fillText(label, Math.max(2, Math.min(x + 3, scope.mediaSize.width - textWidth - 2)), 11);
					ctx.restore();
				});
			},
		};
	}
}
