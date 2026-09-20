/**
 * 图表图例开关：序列显隐的可达性控件（#208 用户故事 15）。
 *
 * - 每 chip 一个序列：色点 + 标签，button aria-pressed 表达显隐状态；
 * - 纯受控组件，不持有状态；页面把可见序列过滤后再喂给 Cockpit；
 * - 色点 backgroundColor 接收 CSS token 字符串（如 "var(--chart-run-3)"），
 *   动态序列色无法用离散类表达，故该处以数据驱动样式呈现。
 */

export type ChartLegendItem = {
	readonly id: string;
	readonly label: string;
	/** CSS token 引用（与 CockpitSeriesSpec.color 同源）。 */
	readonly color: string;
	readonly visible: boolean;
};

export function ChartLegend({
	ariaLabel,
	items,
	onToggle,
	testId,
}: {
	readonly ariaLabel: string;
	readonly items: readonly ChartLegendItem[];
	readonly onToggle: (id: string) => void;
	readonly testId?: string;
}) {
	return (
		<fieldset
			aria-label={ariaLabel}
			data-testid={testId}
			className="m-0 flex flex-wrap items-center gap-1.5 border-0 p-0"
		>
			{items.map((item) => (
				<button
					key={item.id}
					type="button"
					aria-pressed={item.visible}
					data-legend-id={item.id}
					data-legend-visible={item.visible}
					onClick={() => onToggle(item.id)}
					className="flex items-center gap-1.5 rounded-full border border-(--color-border-subtle) px-2.5 py-1 font-data text-xs transition-colors hover:bg-(--color-interaction-hover-subtle-bg)"
				>
					<span
						aria-hidden="true"
						className="inline-block h-2 w-2 flex-none rounded-full"
						style={{ backgroundColor: item.color }}
					/>
					<span className="max-w-56 truncate text-(--color-foreground-secondary)">
						{item.visible ? item.label : <s className="decoration-1">{item.label}</s>}
					</span>
				</button>
			))}
		</fieldset>
	);
}
