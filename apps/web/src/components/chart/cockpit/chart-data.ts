import type { CandlestickData, HistogramData, LineData, Time, WhitespaceData } from "lightweight-charts";

/**
 * Chart Cockpit 数据变换层：bars → lightweight-charts 序列的纯函数映射。
 * 只承诺外部行为——缺失渲染断口（whitespace，不插值）、新鲜度分档、涨跌方向与导出 CSV；
 * 不触碰图表库内部状态。
 */

/** 数据新鲜度分档（与 `--data-freshness-*` 透明度 token 同一体系，不另造第二套）。 */
export type FreshnessBucket = "live" | "recent" | "aging" | "stale" | "expired";

/**
 * 分档边界（毫秒，对应 token 注释）：live < 5s（推送中）、recent < 30s、
 * aging < 5min、stale < 30min，其余为 expired。
 */
export const FRESHNESS_THRESHOLDS = {
	live: 5_000,
	recent: 30_000,
	aging: 300_000,
	stale: 1_800_000,
} as const;

export function freshnessBucket(ageMs: number): FreshnessBucket {
	if (ageMs < FRESHNESS_THRESHOLDS.live) return "live";
	if (ageMs < FRESHNESS_THRESHOLDS.recent) return "recent";
	if (ageMs < FRESHNESS_THRESHOLDS.aging) return "aging";
	if (ageMs < FRESHNESS_THRESHOLDS.stale) return "stale";
	return "expired";
}

/**
 * 单根 bar：time 为 Unix 秒；close / volume 为 null 表示该时点数据缺失，
 * 渲染为断口（不插值、不补零）。open/high/low 供蜡烛图（缺失时以 close 退化）。
 */
export type CockpitBar = {
	readonly time: number;
	readonly close: number | null;
	readonly volume: number | null;
	readonly open?: number | null;
	readonly high?: number | null;
	readonly low?: number | null;
	readonly sourceSnapshotIds?: readonly string[];
	readonly firstTradeDate?: string;
	readonly lastTradeDate?: string;
	readonly availableAt?: string;
	readonly publishedAt?: string;
	readonly partial?: boolean;
};

/** 涨跌方向（CN 默认红涨绿跌，颜色映射经 chart 层 token，不在此耦合）。 */
export type SeriesDirection = "up" | "down" | "flat";

export function directionBetween(previous: number | null, current: number): SeriesDirection {
	if (previous === null) return "flat";
	if (current > previous) return "up";
	if (current < previous) return "down";
	return "flat";
}

/** 涨跌方向 → chart 层涨跌色 token（Market 语义域，禁跨域复用）。 */
export function directionColorToken(direction: SeriesDirection): string {
	if (direction === "up") return "var(--chart-series-up)";
	if (direction === "down") return "var(--chart-series-down)";
	return "var(--chart-series-neutral)";
}

export type LinePoint = LineData<Time> | WhitespaceData<Time>;

/** 最后一根有收盘价的 bar（读数与联动十字线的共同参考）。 */
export function lastNonNullClose(bars: readonly CockpitBar[]): CockpitBar | null {
	for (let index = bars.length - 1; index >= 0; index -= 1) {
		const bar = bars[index];
		if (bar && bar.close !== null) return bar;
	}
	return null;
}

export type GapRange = {
	readonly from: number;
	readonly to: number;
};

/**
 * 缺失区间（连续 close === null 的起止时间），用于断口范围标注；
 * 前导缺口以下一个存在 bar 收界，尾部缺口以最后一个缺失 bar 收界（开界）。
 */
export function findGapRanges(bars: readonly CockpitBar[]): GapRange[] {
	const sorted = [...bars].sort((a, b) => a.time - b.time);
	const gaps: GapRange[] = [];
	let runStart: number | null = null;
	for (const bar of sorted) {
		if (bar.close === null) {
			if (runStart === null) runStart = bar.time;
		} else if (runStart !== null) {
			gaps.push({ from: runStart, to: bar.time });
			runStart = null;
		}
	}
	const lastBar = sorted.at(-1);
	if (runStart !== null && lastBar) {
		gaps.push({ from: runStart, to: lastBar.time });
	}
	return gaps;
}

/**
 * 多序列缺口并集：任一序列在某区间存在 null 断点即计为图表级缺口（重叠区间合并）。
 * 单序列退化为 findGapRanges 本身；缺口归属由对应曲线的断口呈现。
 */
export function mergedGapRanges(seriesBars: readonly (readonly CockpitBar[])[]): GapRange[] {
	const ranges = seriesBars.flatMap((bars) => findGapRanges(bars)).sort((left, right) => left.from - right.from);
	const merged: GapRange[] = [];
	for (const range of ranges) {
		const last = merged.at(-1);
		if (last && range.from <= last.to) {
			if (range.to > last.to) merged[merged.length - 1] = { from: last.from, to: range.to };
		} else {
			merged.push(range);
		}
	}
	return merged;
}

/** close 缺失（null）映射为 whitespace 点：lightweight-charts 据此渲染断口。 */
export function toLineSeriesData(bars: readonly CockpitBar[]): LinePoint[] {
	return [...bars]
		.sort((a, b) => a.time - b.time)
		.map((bar) => (bar.close === null ? { time: bar.time as Time } : { time: bar.time as Time, value: bar.close }));
}

export type CandlePoint = CandlestickData<Time> | WhitespaceData<Time>;

/** 蜡烛图映射：close 缺失 → whitespace 断口；OHLC 缺失以 close 退化（不造形）。 */
export function toCandleSeriesData(bars: readonly CockpitBar[]): CandlePoint[] {
	return [...bars]
		.sort((a, b) => a.time - b.time)
		.map((bar) => {
			if (bar.close === null) {
				return { time: bar.time as Time };
			}
			return {
				time: bar.time as Time,
				open: bar.open ?? bar.close,
				high: bar.high ?? Math.max(bar.open ?? bar.close, bar.close),
				low: bar.low ?? Math.min(bar.open ?? bar.close, bar.close),
				close: bar.close,
			};
		});
}

/** 服务端图表周期。 */
export type BarPeriod = "daily" | "weekly" | "monthly";

export type FreshnessSegment = {
	readonly bucket: FreshnessBucket;
	readonly points: readonly CockpitBar[];
};

/**
 * 按新鲜度分档把 bars 切成连续段（供逐段序列以各自透明度渲染）。
 * 相邻段把前一段的最后一个点作为连接点补进本段，保证折线连续、段内透明度一致。
 */
export function splitByFreshness(bars: readonly CockpitBar[], nowMs: number): FreshnessSegment[] {
	const segments: Array<{ bucket: FreshnessBucket; points: CockpitBar[] }> = [];
	for (const bar of bars) {
		const bucket = freshnessBucket(nowMs - bar.time * 1000);
		const last = segments.at(-1);
		if (!last) {
			segments.push({ bucket, points: [bar] });
		} else if (last.bucket === bucket) {
			last.points.push(bar);
		} else {
			const connector = last.points.at(-1) ?? bar;
			segments.push({ bucket, points: [connector, bar] });
		}
	}
	return segments;
}

export type VolumePoint = HistogramData<Time> | WhitespaceData<Time>;

/**
 * 成交量直方图数据：颜色按收盘涨跌方向注入（方向参考上一根非空收盘价）；
 * volume 缺失映射为 whitespace（无柱、不补零）。
 */
export function toVolumeSeriesData(
	bars: readonly CockpitBar[],
	colorFor: (direction: SeriesDirection) => string,
): VolumePoint[] {
	let previousClose: number | null = null;
	return [...bars]
		.sort((a, b) => a.time - b.time)
		.map((bar) => {
			if (bar.volume === null) {
				return { time: bar.time as Time };
			}
			const direction = bar.close === null ? "flat" : directionBetween(previousClose, bar.close);
			if (bar.close !== null) {
				previousClose = bar.close;
			}
			return { time: bar.time as Time, value: bar.volume, color: colorFor(direction) };
		});
}

/**
 * 副图指标柱状数据（MACD 柱/回撤水下柱）：值取 close，颜色按值符号
 * （正→涨色、负→跌色，回撤恒负）；close 缺失映射为 whitespace 断口。
 */
export function toHistogramSeriesData(
	bars: readonly CockpitBar[],
	colorFor: (direction: SeriesDirection) => string,
): VolumePoint[] {
	return [...bars]
		.sort((a, b) => a.time - b.time)
		.map((bar) => {
			if (bar.close === null) {
				return { time: bar.time as Time };
			}
			const direction: SeriesDirection = bar.close > 0 ? "up" : bar.close < 0 ? "down" : "flat";
			return { time: bar.time as Time, value: bar.close, color: colorFor(direction) };
		});
}

/** 导出物携带的 PIT 身份（裁决 #208-4：完整 snapshot id，不截断唯一修订标识）。 */
export type ChartExportIdentity = {
	readonly asOf?: number | null;
	readonly asOfIso?: string | null;
	readonly snapshotId?: string | null;
	readonly calendarSnapshotIds?: string | null;
	readonly adjustment?: string | null;
	readonly period?: string | null;
	readonly knowledgeCutoff?: string | null;
	readonly publicationCutoff?: string | null;
	readonly dataSourceName: string;
	readonly productVersion: string;
	readonly exportedAtMs: number;
};

const CSV_METADATA_COLUMNS = [
	"as_of",
	"snapshot_id",
	"knowledge_cutoff",
	"publication_cutoff",
	"data_source",
	"exported_at",
	"product_version",
] as const;

function csvCell(value: string | number | null | undefined): string {
	if (value === null || value === undefined || value === "") return "";
	return /[",\n]/u.test(String(value)) ? `"${String(value).replace(/"/gu, '""')}"` : String(value);
}

/** Unix 秒 → ISO 8601 UTC（导出与读数统一口径，避免环境时区漂移）。 */
export function formatExportTime(unixSeconds: number): string {
	return `${new Date(unixSeconds * 1000).toISOString().slice(0, 19)}Z`;
}

/** PNG footer 两行：PIT 身份一行 + 溯源一行（完整 snapshot id，不截断）。 */
export function buildPngFooterLines(identity: ChartExportIdentity): [string, string] {
	const orDash = (value: string | null | undefined) => value || "—";
	return [
		`as_of ${identity.asOfIso ?? (identity.asOf != null ? formatExportTime(identity.asOf) : "—")} · snapshot ${orDash(identity.snapshotId)}`,
		`cutoff k=${orDash(identity.knowledgeCutoff)} p=${orDash(identity.publicationCutoff)} · source ${identity.dataSourceName} · calendar ${orDash(identity.calendarSnapshotIds)} · adjustment ${orDash(identity.adjustment)} · period ${orDash(identity.period)} · exported ${new Date(identity.exportedAtMs).toISOString()} · v${identity.productVersion}`,
	];
}

/**
 * PNG footer 行按画布宽换行：多 run 身份（8×~74 字符 id）单行绘制会被右缘裁掉。
 * 逐字符贪心（ID 类内容无词边界可依）；measure 由调用方注入（canvas measureText），
 * 纯函数便于单测。
 */
export function wrapFooterLine(measure: (text: string) => number, text: string, maxWidth: number): string[] {
	if (maxWidth <= 0 || measure(text) <= maxWidth) return [text];
	const lines: string[] = [];
	let current = "";
	for (const char of text) {
		if (current && measure(current + char) > maxWidth) {
			lines.push(current);
			current = char;
		} else {
			current += char;
		}
	}
	if (current) lines.push(current);
	return lines;
}

/**
 * 导出 CSV：每序列一列 close（蜡烛序列附 open/high/low，缺失留空保持断口语义），
 * volume 取首个序列，行尾附带完整 PIT 身份列，使同 as_of 下不同 cutoff /
 * 修订宇宙的导出物可区分。
 */
export function toCsvExport(
	seriesById: ReadonlyArray<{ readonly id: string; readonly bars: readonly CockpitBar[] }>,
	identity: ChartExportIdentity,
): string {
	const volume = seriesById[0]?.bars ?? [];
	const volumeByTime = new Map(volume.map((bar) => [bar.time, bar.volume]));
	const times = new Set<number>();
	for (const entry of seriesById) {
		for (const bar of entry.bars) times.add(bar.time);
	}
	const withOhlc = seriesById.map((entry) => entry.bars.some((bar) => bar.open !== undefined));
	const hasChartSources = volume.some((bar) => bar.sourceSnapshotIds !== undefined);
	const metadata = [
		identity.asOfIso ?? (identity.asOf != null ? formatExportTime(identity.asOf) : ""),
		identity.snapshotId ?? "",
		identity.knowledgeCutoff ?? "",
		identity.publicationCutoff ?? "",
		identity.dataSourceName,
		new Date(identity.exportedAtMs).toISOString(),
		identity.productVersion,
	];
	const header = [
		"time",
		...seriesById.flatMap((entry, index) =>
			withOhlc[index]
				? [`open_${entry.id}`, `high_${entry.id}`, `low_${entry.id}`, `close_${entry.id}`]
				: [`close_${entry.id}`],
		),
		"volume",
		...(hasChartSources
			? [
					"first_trade_date",
					"last_trade_date",
					"available_at",
					"published_at",
					"partial",
					"bar_source_snapshot_ids",
					"calendar_snapshot_ids",
					"adjustment",
					"period",
				]
			: []),
		...CSV_METADATA_COLUMNS,
	];
	const rows = [...times]
		.sort((a, b) => a - b)
		.map((time) => [
			formatExportTime(time),
			...seriesById.flatMap((entry, index) => {
				const bar = entry.bars.find((item) => item.time === time);
				if (!withOhlc[index]) {
					return [bar?.close ?? ""];
				}
				return [bar?.open ?? "", bar?.high ?? "", bar?.low ?? "", bar?.close ?? ""];
			}),
			volumeByTime.get(time) ?? "",
			...(hasChartSources
				? (() => {
						const bar = volume.find((item) => item.time === time);
						return [
							bar?.firstTradeDate ?? "",
							bar?.lastTradeDate ?? "",
							bar?.availableAt ?? "",
							bar?.publishedAt ?? "",
							bar?.partial === undefined ? "" : String(bar.partial),
							bar?.sourceSnapshotIds?.join("|") ?? "",
							identity.calendarSnapshotIds ?? "",
							identity.adjustment ?? "",
							identity.period ?? "",
						];
					})()
				: []),
			...metadata,
		]);
	return [header, ...rows].map((row) => row.map((cell) => csvCell(cell)).join(",")).join("\n");
}

/** Unix 秒 → `YYYY-MM-DD HH:mm`（UTC），用于图例/读数。 */
export function formatReadoutTime(unixSeconds: number): string {
	return new Date(unixSeconds * 1000).toISOString().slice(0, 16).replace("T", " ");
}
