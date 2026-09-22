import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { LineChart } from "@/components/chart/line-chart";
import type { SparklinePoint } from "@/types";
import type { ManualAccountHistory, ManualHistoryQueryIdentity, ManualLedgerRevision } from "../api/manual-accounts";

const INPUT_CLASS =
	"rounded-(--radius-sm) border border-(--color-border-subtle) bg-(--color-surface-1) px-2 py-1.5 font-data text-sm text-(--color-foreground) disabled:opacity-60";

const CLOSED_REASON_LABELS: Readonly<Record<string, string>> = {
	range_end: "区间结束",
	loss_to_zero: "亏损归零",
	full_withdrawal: "全额赎回",
	valuation_gap: "估值断口",
	negative_equity: "负净资产",
};

const QUALITY_LABELS: Readonly<Record<string, string>> = {
	timing_unknown: "资金流时点未知",
	cash_flow_valuation_missing: "盘中流缺估值",
	security_transfer_unsupported: "证券划转未支持",
	negative_equity_unsupported: "负净资产",
	valuation_gap: "估值断口",
	full_withdrawal_segment_end: "全额赎回",
	loss_to_zero_segment_end: "亏损归零",
	single_point_segment: "单点分段",
	price_missing: "缺价",
	stale_price: "停牌沿用",
};

function formatMoney(value: string | null): string {
	if (value === null) return "—";
	const parsed = Number(value);
	if (!Number.isFinite(parsed)) return value;
	return new Intl.NumberFormat("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(parsed);
}

function formatPercent(value: string | null): string {
	if (value === null) return "—";
	const parsed = Number(value);
	if (!Number.isFinite(parsed)) return value;
	return `${(parsed * 100).toFixed(2)}%`;
}

function shiftDate(isoDate: string, days: number): string {
	const parsed = new Date(`${isoDate}T00:00:00Z`);
	if (Number.isNaN(parsed.getTime())) return isoDate;
	parsed.setUTCDate(parsed.getUTCDate() + days);
	return parsed.toISOString().slice(0, 10);
}

function firstSegmentCurve(history: ManualAccountHistory): readonly SparklinePoint[] {
	if (history.segments.length === 0) return [];
	const first = history.segments[0];
	if (first === undefined) return [];
	return history.points
		.filter(
			(point) =>
				point.segment_id === first.segment_id &&
				point.cumulative_return !== null &&
				point.on_date >= first.start_date &&
				point.on_date <= first.end_date,
		)
		.map((point) => ({
			time: point.on_date,
			value: Number(point.cumulative_return) * 100,
		}));
}

const FALLBACK_IDENTITY: ManualHistoryQueryIdentity = {
	start_date: "",
	end_date: "",
	knowledge_cutoff: "",
	publication_cutoff: "",
	source_snapshot_ids: [],
	ledger_event_count: 0,
	ledger_hash: "",
};

/**
 * Shared read-only historical TWR panel for one exact ledger revision.
 *
 * The scope label distinguishes simulated (Paper) from real (Manual) results;
 * both variants render the same backend numbers without local re-computation.
 */
export function AccountHistoryPanel({
	scopeLabel,
	scopeNote,
	asOf,
	ledgerRevision,
	queryKeyFor,
	fetchHistory,
}: {
	readonly scopeLabel: string;
	readonly scopeNote: string;
	readonly asOf: string;
	readonly ledgerRevision: ManualLedgerRevision;
	readonly queryKeyFor: (identity: ManualHistoryQueryIdentity) => readonly unknown[];
	readonly fetchHistory: (identity: ManualHistoryQueryIdentity) => Promise<ManualAccountHistory>;
}) {
	const [startDate, setStartDate] = useState(shiftDate(asOf, -30));
	const [endDate, setEndDate] = useState(asOf);
	const [cutoff, setCutoff] = useState(new Date().toISOString());
	const [snapshotsText, setSnapshotsText] = useState("");
	const [identity, setIdentity] = useState<ManualHistoryQueryIdentity | null>(null);

	const snapshots = snapshotsText
		.split(/[,,，\s]+/)
		.map((value) => value.trim())
		.filter(Boolean);
	const canSubmit =
		startDate !== "" &&
		endDate !== "" &&
		startDate <= endDate &&
		cutoff !== "" &&
		snapshots.length > 0 &&
		ledgerRevision.event_count > 0;

	const historyQuery = useQuery({
		queryKey: queryKeyFor(identity ?? FALLBACK_IDENTITY),
		queryFn: () => fetchHistory(identity ?? FALLBACK_IDENTITY),
		enabled: identity !== null,
	});

	return (
		<section
			aria-label="历史收益"
			className="rounded-(--radius-md) border border-(--color-border-subtle) bg-(--color-surface-panel-base)"
		>
			<header className="border-b border-(--color-border-subtle) px-4 py-3">
				<div className="flex flex-wrap items-center gap-2">
					<h2 className="text-sm font-semibold text-(--color-foreground)">历史收益（资金流调整 TWR）</h2>
					<span className="rounded-full bg-(--color-surface-strip) px-2 py-0.5 text-xs text-(--color-foreground-secondary)">
						{scopeLabel}
					</span>
				</div>
				<p className="mt-1 text-[11px] text-(--color-foreground-tertiary)">{scopeNote}</p>
			</header>
			<div className="grid gap-2 px-4 py-3 sm:grid-cols-2 xl:grid-cols-5">
				<label className="flex flex-col gap-1 text-xs text-(--color-foreground-secondary)">
					开始日期
					<input
						aria-label="历史开始日期"
						type="date"
						className={INPUT_CLASS}
						value={startDate}
						onChange={(event) => setStartDate(event.currentTarget.value)}
					/>
				</label>
				<label className="flex flex-col gap-1 text-xs text-(--color-foreground-secondary)">
					结束日期
					<input
						aria-label="历史结束日期"
						type="date"
						className={INPUT_CLASS}
						value={endDate}
						onChange={(event) => setEndDate(event.currentTarget.value)}
					/>
				</label>
				<label className="flex flex-col gap-1 text-xs text-(--color-foreground-secondary)">
					知识/发布截止
					<input
						aria-label="知识截止"
						className={INPUT_CLASS}
						value={cutoff}
						onChange={(event) => setCutoff(event.currentTarget.value)}
					/>
				</label>
				<label className="flex flex-col gap-1 text-xs text-(--color-foreground-secondary)">
					价格快照（逗号分隔）
					<input
						aria-label="价格快照"
						className={INPUT_CLASS}
						placeholder="snapshot:stock_daily:…"
						value={snapshotsText}
						onChange={(event) => setSnapshotsText(event.currentTarget.value)}
					/>
				</label>
				<div className="flex items-end">
					<button
						type="button"
						className="rounded-(--radius-sm) border border-(--color-border-subtle) bg-(--color-surface-strip) px-3 py-1.5 text-xs font-medium text-(--color-foreground) disabled:opacity-50"
						disabled={!canSubmit}
						onClick={() => {
							if (!canSubmit) return;
							setIdentity({
								start_date: startDate,
								end_date: endDate,
								knowledge_cutoff: cutoff,
								publication_cutoff: cutoff,
								source_snapshot_ids: snapshots,
								ledger_event_count: ledgerRevision.event_count,
								ledger_hash: ledgerRevision.ledger_hash,
							});
						}}
					>
						查询历史
					</button>
				</div>
			</div>
			{identity === null && (
				<p className="px-4 pb-4 text-xs text-(--color-foreground-tertiary)">
					填写区间与价格快照后查询；外部资金流需要在录入时声明时点，否则该日收益留空。
				</p>
			)}
			{historyQuery.isError && (
				<div
					role="alert"
					className="mx-4 mb-4 flex items-center justify-between rounded-(--radius-sm) border border-(--color-risk-critical-fg) px-3 py-2 text-xs"
				>
					<span>历史收益查询失败：{String(historyQuery.error)}</span>
					<button type="button" className="underline" onClick={() => void historyQuery.refetch()}>
						重试
					</button>
				</div>
			)}
			{historyQuery.data && <AccountHistoryResult history={historyQuery.data} />}
		</section>
	);
}

/**
 * Shared read-only rendering of one historical series: identity line,
 * segment cards, first-segment curve, and the per-date table.  Accepts any
 * view with these fields, so MODEL target replays reuse it unchanged.
 */
export function AccountHistoryResult({
	history,
}: {
	readonly history: Pick<
		ManualAccountHistory,
		"result_id" | "method" | "valuation_policy_version" | "points" | "segments"
	>;
}) {
	const curve = firstSegmentCurve(history as ManualAccountHistory);
	return (
		<div className="grid gap-4 border-t border-(--color-border-subtle) px-4 py-4">
			<p className="break-all font-data text-xs text-(--color-foreground-tertiary)">
				{history.result_id} · {history.method} · {history.valuation_policy_version}
			</p>
			<div className="grid gap-2 md:grid-cols-2 xl:grid-cols-4">
				{history.segments.map((segment) => (
					<div
						key={segment.segment_id}
						className="rounded-(--radius-sm) border border-(--color-border-subtle) bg-(--color-surface-strip) px-3 py-2"
					>
						<p className="text-[11px] text-(--color-foreground-tertiary)">
							分段 {segment.segment_id} · {segment.start_date} ~ {segment.end_date}
						</p>
						<p className="mt-1 font-data text-base font-semibold tabular-nums text-(--color-foreground)">
							{formatPercent(segment.linked_return)}
						</p>
						<p className="mt-1 text-[11px] text-(--color-foreground-secondary)">
							{CLOSED_REASON_LABELS[segment.closed_reason] ?? segment.closed_reason}
						</p>
					</div>
				))}
				{history.segments.length === 0 && (
					<p className="text-xs text-(--color-foreground-tertiary)">区间内无可估值时点。</p>
				)}
			</div>
			{curve.length >= 2 ? (
				<section aria-label="首段累计收益曲线">
					<p className="mb-1 text-xs text-(--color-foreground-secondary)">首段累计收益（%）</p>
					<LineChart data={curve} height={180} showAxes />
				</section>
			) : (
				<p className="text-xs text-(--color-foreground-tertiary)">
					首段缺少可链接收益点（断口、单点或资金流时点未知），仅显示资产。
				</p>
			)}
			<div className="overflow-x-auto">
				<table className="w-full min-w-[760px] text-left text-xs">
					<thead className="bg-(--color-surface-strip) text-(--color-foreground-tertiary)">
						<tr>
							{["日期", "总资产", "现金", "外部流", "当日收益", "累计收益", "分段", "价格时间", "标记"].map((label) => (
								<th key={label} className="px-3 py-2 font-medium">
									{label}
								</th>
							))}
						</tr>
					</thead>
					<tbody>
						{history.points.map((point) => (
							<tr key={point.on_date} className="border-t border-(--color-border-subtle) text-(--color-foreground)">
								<td className="px-3 py-2 font-data">{point.on_date}</td>
								<td className="px-3 py-2 font-data tabular-nums">{formatMoney(point.total_value)}</td>
								<td className="px-3 py-2 font-data tabular-nums">{formatMoney(point.cash)}</td>
								<td className="px-3 py-2 font-data tabular-nums">{formatMoney(point.external_flow)}</td>
								<td className="px-3 py-2 font-data tabular-nums">{formatPercent(point.period_return)}</td>
								<td className="px-3 py-2 font-data tabular-nums">{formatPercent(point.cumulative_return)}</td>
								<td className="px-3 py-2 font-data">{point.segment_id ?? "—"}</td>
								<td className="px-3 py-2 font-data text-(--color-foreground-tertiary)">
									{point.price_time ?? "—"}
									{point.stale ? "（停牌沿用）" : ""}
								</td>
								<td className="px-3 py-2">
									{point.quality.map((mark) => (
										<span
											key={`${mark.code}:${mark.detail}`}
											title={mark.detail}
											className="mr-1 rounded-full bg-(--color-risk-warning-bg) px-2 py-0.5 text-xs text-(--color-risk-warning-fg)"
										>
											{QUALITY_LABELS[mark.code] ?? mark.code}
										</span>
									))}
								</td>
							</tr>
						))}
					</tbody>
				</table>
			</div>
		</div>
	);
}
