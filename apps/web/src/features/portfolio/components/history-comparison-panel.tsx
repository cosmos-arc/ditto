import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import type { ComparisonLegKind, HistoryComparison, HistoryComparisonRun } from "../api/account-models";
import { fetchManualAccounts } from "../api/manual-accounts";
import { fetchPaperAccounts, fetchPaperSessions } from "../api/paper-accounts";
import {
	fetchHistoryComparison,
	fetchStrategyOptions,
	type HistoryComparisonIdentity,
	type StrategyOption,
} from "../api/portfolio-comparison";
import { tradingKeys } from "../api/query-keys";

const INPUT_CLASS =
	"rounded-(--radius-sm) border border-(--color-border-subtle) bg-(--color-surface-1) px-2 py-1.5 font-data text-sm text-(--color-foreground) disabled:opacity-60";

const LEG_COLORS: Readonly<Record<ComparisonLegKind, string>> = {
	model: "var(--chart-palette-1)",
	paper: "var(--chart-palette-2)",
	manual: "var(--chart-palette-3)",
};

const LEG_TEXT_CLASSES: Readonly<Record<ComparisonLegKind, string>> = {
	model: "text-blue-700",
	paper: "text-emerald-700",
	manual: "text-amber-700",
};

const LEG_LABELS: Readonly<Record<ComparisonLegKind, string>> = {
	model: "MODEL",
	paper: "PAPER",
	manual: "MANUAL",
};

const STATUS_LABELS: Readonly<Record<HistoryComparison["status"], string>> = {
	comparable: "可比区间",
	single_common_point: "仅单点共同资产",
	incomparable: "不可比",
};

const CHART_WIDTH = 720;
const CHART_HEIGHT = 240;
const CHART_PADDING = 36;

function splitList(text: string): readonly string[] {
	return text
		.split(/[,,，\s]+/)
		.map((value) => value.trim())
		.filter(Boolean);
}

function formatGrowth(value: string): string {
	const parsed = Number(value);
	if (!Number.isFinite(parsed)) return value;
	return parsed.toFixed(4);
}

function formatMoney(value: string): string {
	const parsed = Number(value);
	if (!Number.isFinite(parsed)) return value;
	return new Intl.NumberFormat("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(parsed);
}

function formatWindowReturn(value: string | null): string {
	if (value === null) return "—";
	const parsed = Number(value);
	if (!Number.isFinite(parsed)) return value;
	return `${parsed >= 0 ? "+" : ""}${(parsed * 100).toFixed(2)}%`;
}

function downloadBlob(blob: Blob, filename: string): void {
	const url = URL.createObjectURL(blob);
	const anchor = document.createElement("a");
	anchor.href = url;
	anchor.download = filename;
	anchor.click();
	URL.revokeObjectURL(url);
}

function buildComparisonCsv(comparison: HistoryComparison, run: HistoryComparisonRun): string {
	const lines = [
		`# result_id=${comparison.result_id}`,
		`# method=${comparison.method} valuation=${comparison.valuation_policy_version} comparison=${comparison.comparison_policy_version}`,
		`# currency=${comparison.currency} run=${run.start_date}..${run.end_date}`,
		"date,model_growth,paper_growth,manual_growth,model_assets,paper_assets,manual_assets",
	];
	for (const point of run.points) {
		lines.push(
			[
				point.on_date,
				point.growth.model,
				point.growth.paper,
				point.growth.manual,
				point.assets.model,
				point.assets.paper,
				point.assets.manual,
			].join(","),
		);
	}
	lines.push(
		[
			"window_return",
			run.window_returns.model ?? "",
			run.window_returns.paper ?? "",
			run.window_returns.manual ?? "",
			"",
			"",
			"",
		].join(","),
	);
	return `${lines.join("\n")}\n`;
}

async function exportChartPng(
	svg: SVGSVGElement,
	comparison: HistoryComparison,
	run: HistoryComparisonRun,
): Promise<void> {
	const canvas = document.createElement("canvas");
	const context = canvas.getContext("2d");
	if (context === null) {
		throw new Error("当前环境不支持 PNG 导出");
	}
	const clone = svg.cloneNode(true) as SVGSVGElement;
	clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
	const serialized = new XMLSerializer().serializeToString(clone);
	const image = new Image();
	await new Promise<void>((resolve, reject) => {
		image.onload = () => resolve();
		image.onerror = () => reject(new Error("图表光栅化失败"));
		image.src = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(serialized)}`;
	});
	const scale = 2;
	const footerLines = [
		comparison.result_id,
		`${comparison.method} · ${comparison.valuation_policy_version} · ${comparison.comparison_policy_version} · ${comparison.currency}`,
		`共同段 ${run.start_date} ~ ${run.end_date} · MODEL ${formatWindowReturn(run.window_returns.model)} · PAPER ${formatWindowReturn(run.window_returns.paper)} · MANUAL ${formatWindowReturn(run.window_returns.manual)}`,
	];
	const footerHeight = 16 * footerLines.length + 16;
	canvas.width = CHART_WIDTH * scale;
	canvas.height = (CHART_HEIGHT + footerHeight) * scale;
	const styles = getComputedStyle(document.documentElement);
	const background = styles.getPropertyValue("--color-surface-1").trim();
	if (background !== "") {
		context.fillStyle = background;
		context.fillRect(0, 0, canvas.width, canvas.height);
	}
	context.drawImage(image, 0, 0, CHART_WIDTH * scale, CHART_HEIGHT * scale);
	const footerColor = styles.getPropertyValue("--color-foreground-secondary").trim();
	if (footerColor !== "") {
		context.fillStyle = footerColor;
	}
	context.font = `${12 * scale}px monospace`;
	footerLines.forEach((line, index) => {
		context.fillText(line, 8 * scale, (CHART_HEIGHT + 20 + index * 16) * scale);
	});
	const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, "image/png"));
	if (blob === null) {
		throw new Error("PNG 编码失败");
	}
	downloadBlob(blob, `history-comparison-${run.start_date}-${run.end_date}.png`);
}

function ComparisonRunChart({
	run,
	svgRef,
}: {
	readonly run: HistoryComparisonRun;
	readonly svgRef: React.RefObject<SVGSVGElement | null>;
}) {
	// One shared y scale across all legs (anchored at 1) so the normalized
	// lines stay visually comparable; per-leg scaling would erase the signal.
	const allValues = (Object.keys(LEG_LABELS) as readonly ComparisonLegKind[]).flatMap((kind) =>
		run.points.map((point) => Number(point.growth[kind])),
	);
	const min = Math.min(1, ...allValues);
	const max = Math.max(1, ...allValues);
	const span = max > min ? max - min : 0.01;
	const step = run.points.length > 1 ? (CHART_WIDTH - CHART_PADDING * 2) / (run.points.length - 1) : 0;
	const polylineOf = (kind: ComparisonLegKind) =>
		run.points
			.map((point, index) => {
				const x = CHART_PADDING + index * step;
				const y =
					CHART_HEIGHT -
					CHART_PADDING -
					((Number(point.growth[kind]) - min) / span) * (CHART_HEIGHT - CHART_PADDING * 2);
				return `${x.toFixed(1)},${y.toFixed(1)}`;
			})
			.join(" ");
	const dateLabels = [run.points[0]?.on_date, run.points[run.points.length - 1]?.on_date];
	return (
		<svg
			ref={svgRef}
			data-testid="history-comparison-chart"
			role="img"
			aria-label={`共同段 ${run.start_date} 至 ${run.end_date} 的归一曲线`}
			width={CHART_WIDTH}
			height={CHART_HEIGHT}
			viewBox={`0 0 ${CHART_WIDTH} ${CHART_HEIGHT}`}
			fontFamily="monospace"
		>
			<rect x={0} y={0} width={CHART_WIDTH} height={CHART_HEIGHT} fill="var(--color-surface-1)" />
			{(Object.keys(LEG_LABELS) as readonly ComparisonLegKind[]).map((kind) => (
				<polyline
					key={kind}
					data-testid={`history-comparison-line-${kind}`}
					points={polylineOf(kind)}
					fill="none"
					stroke={LEG_COLORS[kind]}
					strokeWidth={2}
				/>
			))}
			<text x={CHART_PADDING} y={18} fontSize={11} fill="var(--chart-series-neutral)">
				{dateLabels[0] ?? ""}
			</text>
			<text x={CHART_WIDTH - CHART_PADDING} y={18} fontSize={11} fill="var(--chart-series-neutral)" textAnchor="end">
				{dateLabels[1] ?? ""}
			</text>
			{(Object.keys(LEG_LABELS) as readonly ComparisonLegKind[]).map((kind, index) => (
				<text key={kind} x={CHART_PADDING + index * 96} y={CHART_HEIGHT - 8} fontSize={11} fill={LEG_COLORS[kind]}>
					■ {LEG_LABELS[kind]}
				</text>
			))}
		</svg>
	);
}

/**
 * Three-portfolio common-window comparison panel (#263).
 *
 * Entity pickers (strategy / PAPER account + session / MANUAL account) remove
 * hand-typed identifiers; every rendered number, and both exports, reference
 * the single backend ``result_id``.
 */
export function HistoryComparisonPanel() {
	const strategiesQuery = useQuery({
		queryKey: tradingKeys.strategyOptions(),
		queryFn: fetchStrategyOptions,
	});
	const manualAccountsQuery = useQuery({
		queryKey: tradingKeys.manualAccounts(),
		queryFn: fetchManualAccounts,
	});
	const paperAccountsQuery = useQuery({
		queryKey: tradingKeys.paperAccounts(),
		queryFn: fetchPaperAccounts,
	});
	const [strategyId, setStrategyId] = useState("");
	const [paperAccountId, setPaperAccountId] = useState("");
	const [paperSessionId, setPaperSessionId] = useState("");
	const [manualAccountId, setManualAccountId] = useState("");
	const sessionsQuery = useQuery({
		queryKey: tradingKeys.paperSessions(paperAccountId || "unselected"),
		queryFn: () => fetchPaperSessions(paperAccountId),
		enabled: paperAccountId !== "",
	});

	const [startDate, setStartDate] = useState("");
	const [endDate, setEndDate] = useState("");
	const [cutoff, setCutoff] = useState(new Date().toISOString());
	const [capitalText, setCapitalText] = useState("100000");
	const [snapshotsText, setSnapshotsText] = useState("");
	const [artifactsText, setArtifactsText] = useState("");
	const [identity, setIdentity] = useState<HistoryComparisonIdentity | null>(null);
	const [selectedRunIndex, setSelectedRunIndex] = useState(0);
	const [exportError, setExportError] = useState<string | null>(null);
	const chartRef = useRef<SVGSVGElement | null>(null);

	const strategies = strategiesQuery.data ?? [];
	const manualAccounts = manualAccountsQuery.data ?? [];
	const paperAccounts = paperAccountsQuery.data ?? [];
	const sessions = sessionsQuery.data ?? [];
	const capital = Number(capitalText);
	const snapshots = splitList(snapshotsText);
	const artifactIds = splitList(artifactsText);

	// Auto-select the first option once catalogs arrive; still user-changeable.
	useEffect(() => {
		if (strategyId === "" && strategies.length > 0) {
			setStrategyId((strategies[0] as StrategyOption).strategy_id);
		}
	}, [strategies, strategyId]);
	useEffect(() => {
		if (paperAccountId === "" && paperAccounts.length > 0) {
			setPaperAccountId(paperAccounts[0]?.account_id ?? "");
		}
	}, [paperAccounts, paperAccountId]);
	useEffect(() => {
		if (manualAccountId === "" && manualAccounts.length > 0) {
			setManualAccountId(manualAccounts[0]?.account_id ?? "");
		}
	}, [manualAccounts, manualAccountId]);
	useEffect(() => {
		if (paperSessionId === "" && sessions.length > 0) {
			setPaperSessionId(sessions[0]?.session_id ?? "");
		}
	}, [sessions, paperSessionId]);

	const canSubmit =
		strategyId !== "" &&
		paperAccountId !== "" &&
		paperSessionId !== "" &&
		manualAccountId !== "" &&
		startDate !== "" &&
		endDate !== "" &&
		startDate <= endDate &&
		cutoff !== "" &&
		Number.isFinite(capital) &&
		capital > 0 &&
		snapshots.length > 0;

	const comparisonQuery = useQuery({
		queryKey: tradingKeys.historyComparison(
			identity ?? {
				strategy_id: "",
				paper_account_id: "",
				paper_session_id: "",
				manual_account_id: "",
				start_date: "",
				end_date: "",
				model_initial_capital: 0,
				knowledge_cutoff: "",
				publication_cutoff: "",
				source_snapshot_ids: [],
			},
		),
		queryFn: () => fetchHistoryComparison(identity as HistoryComparisonIdentity),
		enabled: identity !== null,
		retry: false,
	});
	const comparison = comparisonQuery.data ?? null;
	const runs = comparison?.runs ?? [];
	const runIndex = Math.min(selectedRunIndex, Math.max(runs.length - 1, 0));
	const selectedRun = runs[runIndex] ?? null;

	const csvText = useMemo(
		() => (comparison !== null && selectedRun !== null ? buildComparisonCsv(comparison, selectedRun) : ""),
		[comparison, selectedRun],
	);

	return (
		<section
			aria-label="三组合共同区间比较"
			className="rounded-(--radius-md) border border-(--color-border-subtle) bg-(--color-surface-panel-base)"
			data-testid="history-comparison-panel"
		>
			<header className="border-b border-(--color-border-subtle) px-4 py-3">
				<div className="flex flex-wrap items-center gap-2">
					<h2 className="text-sm font-semibold text-(--color-foreground)">三组合共同区间比较</h2>
					<span className="rounded-full bg-(--color-surface-strip) px-2 py-0.5 text-xs text-(--color-foreground-secondary)">
						Model / Paper / Manual
					</span>
				</div>
				<p className="mt-1 text-[11px] text-(--color-foreground-tertiary)">
					从首个共同有效估值点归一比较；断口与再注资分段不连接，缺口不跨段归一。
				</p>
			</header>
			<div className="grid gap-2 px-4 py-3 sm:grid-cols-2 xl:grid-cols-4">
				<label className="flex flex-col gap-1 text-xs text-(--color-foreground-secondary)">
					Model 策略
					<select
						aria-label="Model 策略"
						className={INPUT_CLASS}
						value={strategyId}
						onChange={(event) => setStrategyId(event.currentTarget.value)}
					>
						{strategies.length === 0 && <option value="">（暂无策略）</option>}
						{strategies.map((strategy) => (
							<option key={strategy.strategy_id} value={strategy.strategy_id}>
								{strategy.name}
							</option>
						))}
					</select>
				</label>
				<label className="flex flex-col gap-1 text-xs text-(--color-foreground-secondary)">
					Paper 账户
					<select
						aria-label="Paper 账户"
						className={INPUT_CLASS}
						value={paperAccountId}
						onChange={(event) => {
							setPaperAccountId(event.currentTarget.value);
							setPaperSessionId("");
						}}
					>
						{paperAccounts.length === 0 && <option value="">（暂无模拟账户）</option>}
						{paperAccounts.map((account) => (
							<option key={account.account_id} value={account.account_id}>
								{account.account_name}
							</option>
						))}
					</select>
				</label>
				<label className="flex flex-col gap-1 text-xs text-(--color-foreground-secondary)">
					Paper 会话
					<select
						aria-label="Paper 会话"
						className={INPUT_CLASS}
						value={paperSessionId}
						disabled={paperAccountId === ""}
						onChange={(event) => setPaperSessionId(event.currentTarget.value)}
					>
						{sessions.length === 0 && <option value="">（该账户暂无会话）</option>}
						{sessions.map((session) => (
							<option key={session.session_id} value={session.session_id}>
								{session.trade_date} · {session.session_id}
							</option>
						))}
					</select>
				</label>
				<label className="flex flex-col gap-1 text-xs text-(--color-foreground-secondary)">
					Manual 账户
					<select
						aria-label="Manual 账户"
						className={INPUT_CLASS}
						value={manualAccountId}
						onChange={(event) => setManualAccountId(event.currentTarget.value)}
					>
						{manualAccounts.length === 0 && <option value="">（暂无实盘账户）</option>}
						{manualAccounts.map((account) => (
							<option key={account.account_id} value={account.account_id}>
								{account.account_name}
							</option>
						))}
					</select>
				</label>
				<label className="flex flex-col gap-1 text-xs text-(--color-foreground-secondary)">
					开始日期
					<input
						aria-label="比较开始日期"
						type="date"
						className={INPUT_CLASS}
						value={startDate}
						onChange={(event) => setStartDate(event.currentTarget.value)}
					/>
				</label>
				<label className="flex flex-col gap-1 text-xs text-(--color-foreground-secondary)">
					结束日期
					<input
						aria-label="比较结束日期"
						type="date"
						className={INPUT_CLASS}
						value={endDate}
						onChange={(event) => setEndDate(event.currentTarget.value)}
					/>
				</label>
				<label className="flex flex-col gap-1 text-xs text-(--color-foreground-secondary)">
					知识/发布截止
					<input
						aria-label="比较知识截止"
						className={INPUT_CLASS}
						value={cutoff}
						onChange={(event) => setCutoff(event.currentTarget.value)}
					/>
				</label>
				<label className="flex flex-col gap-1 text-xs text-(--color-foreground-secondary)">
					Model 初始资本
					<input
						aria-label="比较 Model 初始资本"
						className={INPUT_CLASS}
						inputMode="decimal"
						value={capitalText}
						onChange={(event) => setCapitalText(event.currentTarget.value)}
					/>
				</label>
				<label className="flex flex-col gap-1 text-xs text-(--color-foreground-secondary) sm:col-span-2">
					价格快照（逗号分隔）
					<input
						aria-label="比较价格快照"
						className={INPUT_CLASS}
						placeholder="snapshot:stock_daily:…"
						value={snapshotsText}
						onChange={(event) => setSnapshotsText(event.currentTarget.value)}
					/>
				</label>
				<label className="flex flex-col gap-1 text-xs text-(--color-foreground-secondary) sm:col-span-2">
					钉住 Model 工件（可选，逗号分隔）
					<input
						aria-label="比较钉住工件"
						className={INPUT_CLASS}
						placeholder="留空则按知识截止解析当时有效目标"
						value={artifactsText}
						onChange={(event) => setArtifactsText(event.currentTarget.value)}
					/>
				</label>
				<div className="flex items-end">
					<button
						type="button"
						className="rounded-(--radius-sm) border border-(--color-border-subtle) bg-(--color-surface-strip) px-3 py-1.5 text-xs font-medium text-(--color-foreground) disabled:opacity-50"
						disabled={!canSubmit}
						data-testid="history-comparison-submit"
						onClick={() => {
							if (!canSubmit) return;
							setExportError(null);
							setSelectedRunIndex(0);
							setIdentity({
								strategy_id: strategyId,
								paper_account_id: paperAccountId,
								paper_session_id: paperSessionId,
								manual_account_id: manualAccountId,
								start_date: startDate,
								end_date: endDate,
								model_initial_capital: capital,
								knowledge_cutoff: cutoff,
								publication_cutoff: cutoff,
								source_snapshot_ids: [...snapshots],
								...(artifactIds.length > 0 ? { model_artifact_ids: [...artifactIds] } : {}),
							});
						}}
					>
						比较历史
					</button>
				</div>
			</div>
			{identity === null && (
				<p className="px-4 pb-4 text-xs text-(--color-foreground-tertiary)">
					选择三类组合与区间后比较；Paper/Manual 账本修订由服务端解析并绑定进结果身份。
				</p>
			)}
			{comparisonQuery.isError && (
				<div
					role="alert"
					className="mx-4 mb-4 flex items-center justify-between rounded-(--radius-sm) border border-(--color-risk-critical-fg) px-3 py-2 text-xs"
				>
					<span>共同区间比较失败：{String(comparisonQuery.error)}</span>
					<button type="button" className="underline" onClick={() => void comparisonQuery.refetch()}>
						重试
					</button>
				</div>
			)}
			{comparison !== null && (
				<div
					className="grid gap-4 border-t border-(--color-border-subtle) px-4 py-4"
					data-testid="history-comparison-result"
				>
					<div className="flex flex-wrap items-center gap-2">
						<span className="rounded-full bg-(--color-surface-strip) px-2 py-0.5 text-xs text-(--color-foreground)">
							{STATUS_LABELS[comparison.status]}
						</span>
						{comparison.status === "incomparable" && comparison.empty_reason !== null && (
							<span className="text-xs text-(--color-foreground-secondary)">无交集原因：{comparison.empty_reason}</span>
						)}
						<span className="text-xs text-(--color-foreground-tertiary)">
							区间 {comparison.start_date} ~ {comparison.end_date} · {comparison.currency}
						</span>
					</div>
					<p className="break-all font-data text-xs text-(--color-foreground-tertiary)">
						{comparison.result_id} · {comparison.method} · {comparison.valuation_policy_version} ·{" "}
						{comparison.comparison_policy_version}
					</p>
					{comparison.status === "incomparable" && (
						<p className="text-xs text-(--color-foreground-secondary)">
							三类组合在请求区间内没有共同有效估值日，仅可独立查看各自资产。
						</p>
					)}
					{runs.length > 1 && (
						<div className="flex flex-wrap gap-2" role="tablist" aria-label="共同连续段">
							{runs.map((run, index) => (
								<button
									key={`${run.start_date}-${run.end_date}`}
									type="button"
									role="tab"
									aria-selected={index === runIndex}
									className={`rounded-(--radius-sm) border px-2 py-1 text-xs ${
										index === runIndex
											? "border-(--color-border-strong) bg-(--color-surface-strip) text-(--color-foreground)"
											: "border-(--color-border-subtle) text-(--color-foreground-secondary)"
									}`}
									onClick={() => setSelectedRunIndex(index)}
								>
									共同段 {index + 1}：{run.start_date} ~ {run.end_date}
								</button>
							))}
						</div>
					)}
					{selectedRun !== null && (
						<>
							<div className="grid gap-2 md:grid-cols-3">
								{(Object.keys(LEG_LABELS) as readonly ComparisonLegKind[]).map((kind) => (
									<div
										key={kind}
										className="rounded-(--radius-sm) border border-(--color-border-subtle) bg-(--color-surface-strip) px-3 py-2"
										data-testid={`history-comparison-window-return-${kind}`}
									>
										<p className={`text-[11px] ${LEG_TEXT_CLASSES[kind]}`}>{LEG_LABELS[kind]} 共同段收益</p>
										<p className="mt-1 font-data text-base font-semibold tabular-nums text-(--color-foreground)">
											{formatWindowReturn(selectedRun.window_returns[kind])}
										</p>
										<p className="mt-1 text-[11px] text-(--color-foreground-tertiary)">
											{selectedRun.start_date} ~ {selectedRun.end_date} · {selectedRun.point_count} 点
										</p>
									</div>
								))}
							</div>
							{selectedRun.points.length >= 2 ? (
								<ComparisonRunChart run={selectedRun} svgRef={chartRef} />
							) : (
								<p
									className="text-xs text-(--color-foreground-tertiary)"
									data-testid="history-comparison-single-point-note"
								>
									该共同段只有单点：仅显示资产，不报告区间收益。
								</p>
							)}
							{exportError !== null && (
								<p role="alert" className="text-xs text-(--color-risk-critical-fg)">
									{exportError}
								</p>
							)}
							<div className="flex flex-wrap gap-2">
								<button
									type="button"
									data-testid="history-comparison-export-csv"
									className="rounded-(--radius-sm) border border-(--color-border-subtle) bg-(--color-surface-strip) px-3 py-1.5 text-xs font-medium text-(--color-foreground)"
									onClick={() => {
										downloadBlob(
											new Blob([csvText], { type: "text/csv;charset=utf-8" }),
											`history-comparison-${selectedRun.start_date}-${selectedRun.end_date}.csv`,
										);
									}}
								>
									导出 CSV
								</button>
								<button
									type="button"
									data-testid="history-comparison-export-png"
									className="rounded-(--radius-sm) border border-(--color-border-subtle) bg-(--color-surface-strip) px-3 py-1.5 text-xs font-medium text-(--color-foreground)"
									onClick={() => {
										setExportError(null);
										const svg = chartRef.current;
										if (svg === null) {
											setExportError("图表尚未渲染，无法导出 PNG");
											return;
										}
										void exportChartPng(svg, comparison, selectedRun).catch((error: unknown) => {
											setExportError(String(error));
										});
									}}
								>
									导出 PNG
								</button>
							</div>
							<div className="overflow-x-auto">
								<table className="w-full min-w-[760px] text-left text-xs">
									<thead className="bg-(--color-surface-strip) text-(--color-foreground-tertiary)">
										<tr>
											<th key="date" className="px-3 py-2 font-medium">
												日期
											</th>
											{(Object.keys(LEG_LABELS) as readonly ComparisonLegKind[]).map((kind) => (
												<th key={`growth-${kind}`} className="px-3 py-2 font-medium">
													{LEG_LABELS[kind]} 归一
												</th>
											))}
											{(Object.keys(LEG_LABELS) as readonly ComparisonLegKind[]).map((kind) => (
												<th key={`assets-${kind}`} className="px-3 py-2 font-medium">
													{LEG_LABELS[kind]} 资产
												</th>
											))}
										</tr>
									</thead>
									<tbody>
										{selectedRun.points.map((point) => (
											<tr
												key={point.on_date}
												className="border-t border-(--color-border-subtle) text-(--color-foreground)"
											>
												<td className="px-3 py-2 font-data">{point.on_date}</td>
												{(Object.keys(LEG_LABELS) as readonly ComparisonLegKind[]).map((kind) => (
													<td key={`growth-${point.on_date}-${kind}`} className="px-3 py-2 font-data tabular-nums">
														{formatGrowth(point.growth[kind])}
													</td>
												))}
												{(Object.keys(LEG_LABELS) as readonly ComparisonLegKind[]).map((kind) => (
													<td key={`assets-${point.on_date}-${kind}`} className="px-3 py-2 font-data tabular-nums">
														{formatMoney(point.assets[kind])}
													</td>
												))}
											</tr>
										))}
									</tbody>
								</table>
							</div>
						</>
					)}
					<section aria-label="来源下钻" className="grid gap-2 md:grid-cols-3">
						{comparison.legs.map((leg) => (
							<div
								key={leg.kind}
								data-testid={`history-comparison-leg-${leg.kind}`}
								className="rounded-(--radius-sm) border border-(--color-border-subtle) px-3 py-2"
							>
								<p className={`text-[11px] font-semibold ${LEG_TEXT_CLASSES[leg.kind]}`}>{LEG_LABELS[leg.kind]}</p>
								<p className="mt-1 break-all font-data text-[11px] text-(--color-foreground-tertiary)">
									{leg.result_id}
								</p>
								<p className="mt-1 text-[11px] text-(--color-foreground-secondary)">
									{leg.point_count} 点 · 缺口 {leg.gap_count} · 分段 {leg.segment_count}
									{leg.ledger_revision !== null
										? ` · 账本 ${leg.ledger_revision.event_count}@${leg.ledger_revision.ledger_hash}`
										: ""}
									{leg.target_count !== null ? ` · 目标 ${leg.target_count}` : ""}
								</p>
								<p className="text-[11px] text-(--color-foreground-tertiary)">
									有效日 {leg.first_valued_date ?? "—"} ~ {leg.last_valued_date ?? "—"}
								</p>
							</div>
						))}
					</section>
				</div>
			)}
		</section>
	);
}
