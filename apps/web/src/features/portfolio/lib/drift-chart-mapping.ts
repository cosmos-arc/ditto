import type { PortfolioComparison } from "../api/portfolio-comparison";

/**
 * 三组合权重漂移视图模型（单 as_of 快照）：两两 drift surface → 可视化矩阵。
 *
 * 语义口径：
 * - 行 = 三组合标的并集 + 现金；列 = 三组两两对比（model_vs_paper / model_vs_manual / paper_vs_manual）。
 * - 每格 drift_bps 为观察侧相对基线侧的权重漂移（正 = 观察侧超配）。
 * - 颜色编码观察侧组合专属色：paper → 紫、manual → 琥珀；
 *   paper_vs_manual 两侧均为执行侧组合（无模型基线）→ 中性线色，不冒用组合色。
 * - PIT：三列共享同一 as_of 与 valuation snapshot（页面身份断言已 fail closed），
 *   此处只呈现，不重算。
 */

export const DRIFT_PAIRS = [
	{ id: "model_vs_paper", label: "MODEL → PAPER", color: "var(--chart-combo-paper)" },
	{ id: "model_vs_manual", label: "MODEL → MANUAL", color: "var(--chart-combo-manual)" },
	{ id: "paper_vs_manual", label: "PAPER → MANUAL", color: "var(--chart-series-neutral)" },
] as const;

export type DriftPairId = (typeof DRIFT_PAIRS)[number]["id"];

export type DriftRow = {
	readonly key: string;
	readonly label: string;
	readonly instrumentId: number | null;
	/** 按 pair id 取漂移（bps）；该 pair 无该行数据时为 undefined。 */
	readonly driftBps: Readonly<Partial<Record<DriftPairId, number>>>;
};

const CASH_ROW_KEY = "cash";

function toBps(value: string | undefined): number | undefined {
	if (value === undefined) return undefined;
	const parsed = Number(value);
	return Number.isFinite(parsed) ? parsed : undefined;
}

function instrumentItems(
	comparison: PortfolioComparison,
	pair: DriftPairId,
): readonly { instrumentId: number; driftBps: number | undefined }[] {
	const surface = comparison[pair];
	return surface.items.map((item) => ({
		instrumentId: item.instrument_id,
		driftBps: toBps(item.drift_bps),
	}));
}

/** 三组合标的并集（升序）+ 现金行；每行带各 pair 的漂移值。 */
export function driftRows(comparison: PortfolioComparison): DriftRow[] {
	const instrumentIds = new Set<number>();
	for (const pair of DRIFT_PAIRS) {
		for (const item of instrumentItems(comparison, pair.id)) {
			instrumentIds.add(item.instrumentId);
		}
	}
	const rows: DriftRow[] = [...instrumentIds]
		.sort((left, right) => left - right)
		.map((instrumentId) => ({
			key: `instrument-${instrumentId}`,
			label: `#${instrumentId}`,
			instrumentId,
			driftBps: Object.fromEntries(
				DRIFT_PAIRS.map((pair) => {
					const item = comparison[pair.id].items.find((candidate) => candidate.instrument_id === instrumentId);
					return [pair.id, toBps(item?.drift_bps)];
				}),
			),
		}));
	rows.push({
		key: CASH_ROW_KEY,
		label: "现金",
		instrumentId: null,
		driftBps: Object.fromEntries(DRIFT_PAIRS.map((pair) => [pair.id, toBps(comparison[pair.id].cash_drift_bps)])),
	});
	return rows;
}

/** 可见 pair 集合内的最大 |drift_bps|（含现金），用于发散条比例；无数据时为 0。 */
export function maxAbsDriftBps(rows: readonly DriftRow[], visiblePairs: readonly DriftPairId[]): number {
	let max = 0;
	for (const row of rows) {
		for (const pair of visiblePairs) {
			const value = row.driftBps[pair];
			if (value !== undefined) max = Math.max(max, Math.abs(value));
		}
	}
	return max;
}

/** 三组 pair 是否全部无漂移数据（items 全空且现金漂移全为 0/缺失）。 */
export function isDriftEmpty(comparison: PortfolioComparison): boolean {
	return DRIFT_PAIRS.every(
		(pair) => comparison[pair.id].items.length === 0 && (toBps(comparison[pair.id].cash_drift_bps) ?? 0) === 0,
	);
}

const BPS_DIGITS = 1;

/** 漂移读数（带符号 bps，与页面 bps 纪律一致；U+2212 负号）。 */
export const formatDriftBps = (value: number): string => {
	const sign = value > 0 ? "+" : value < 0 ? "−" : "";
	return `${sign}${Math.abs(value).toFixed(BPS_DIGITS)} bps`;
};

const DRIFT_SCALE_STEPS = 8;

/**
 * 发散条离散刻度（1–8；0 = 无条）：宽度按 |bps|/scale 的 1/8 档呈现，
 * 精确值由条旁数字表达（与月度 IC 热力图的分桶纪律一致）。
 */
export function driftScaleBucket(value: number | undefined, scale: number): number {
	if (value === undefined || scale <= 0) return 0;
	const ratio = Math.min(Math.abs(value) / scale, 1);
	return Math.max(1, Math.ceil(ratio * DRIFT_SCALE_STEPS));
}
