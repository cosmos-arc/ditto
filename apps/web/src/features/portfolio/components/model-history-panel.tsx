import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { fetchModelHistory, type ModelHistoryIdentity } from "../api/portfolio-comparison";
import { tradingKeys } from "../api/query-keys";
import { AccountHistoryResult } from "./account-history-panel";

const INPUT_CLASS =
	"rounded-(--radius-sm) border border-(--color-border-subtle) bg-(--color-surface-1) px-2 py-1.5 font-data text-sm text-(--color-foreground) disabled:opacity-60";

const FALLBACK_IDENTITY: ModelHistoryIdentity = {
	strategy_id: "",
	start_date: "",
	end_date: "",
	initial_capital: "0",
	knowledge_cutoff: "",
	publication_cutoff: "",
};

function shiftDate(isoDate: string, days: number): string {
	const parsed = new Date(`${isoDate}T00:00:00Z`);
	if (Number.isNaN(parsed.getTime())) return isoDate;
	parsed.setUTCDate(parsed.getUTCDate() + days);
	return parsed.toISOString().slice(0, 10);
}

/** MODEL leg: replay only the saved targets; nothing is back-filled. */
export function ModelHistoryPanel({ strategyId, asOf }: { readonly strategyId: string; readonly asOf: string }) {
	const [startDate, setStartDate] = useState(shiftDate(asOf, -30));
	const [endDate, setEndDate] = useState(asOf);
	const [cutoff, setCutoff] = useState(new Date().toISOString());
	const [initialCapital, setInitialCapital] = useState("100000");
	const [artifactIdsText, setArtifactIdsText] = useState("");
	const [identity, setIdentity] = useState<ModelHistoryIdentity | null>(null);

	const artifactIds = artifactIdsText
		.split(/[,,，\s]+/)
		.map((value) => value.trim())
		.filter(Boolean);
	const capital = Number(initialCapital);
	const canSubmit =
		startDate !== "" &&
		endDate !== "" &&
		startDate <= endDate &&
		cutoff !== "" &&
		initialCapital !== "" &&
		Number.isFinite(capital) &&
		capital > 0;

	const historyQuery = useQuery({
		queryKey: tradingKeys.modelHistory(identity ?? FALLBACK_IDENTITY),
		queryFn: () => fetchModelHistory(identity ?? FALLBACK_IDENTITY),
		enabled: identity !== null,
	});

	return (
		<section
			aria-label="Model 历史重放"
			className="rounded-(--radius-md) border border-(--color-border-subtle) bg-(--color-surface-panel-base)"
		>
			<header className="border-b border-(--color-border-subtle) px-4 py-3">
				<div className="flex flex-wrap items-center gap-2">
					<h2 className="text-sm font-semibold text-(--color-foreground)">历史收益（保存目标重放）</h2>
					<span className="rounded-full bg-(--color-surface-strip) px-2 py-0.5 text-xs text-(--color-foreground-secondary)">
						模型目标（Model）
					</span>
				</div>
				<p className="mt-1 text-[11px] text-(--color-foreground-tertiary)">
					只读重放当时保存的目标与生效时间；缺目标的日期留空，不以当前权重倒算，重放无费用与分红假设
				</p>
			</header>
			<div className="grid gap-2 px-4 py-3 sm:grid-cols-2 xl:grid-cols-5">
				<label className="flex flex-col gap-1 text-xs text-(--color-foreground-secondary)">
					开始日期
					<input
						aria-label="Model 重放开始日期"
						type="date"
						className={INPUT_CLASS}
						value={startDate}
						onChange={(event) => setStartDate(event.currentTarget.value)}
					/>
				</label>
				<label className="flex flex-col gap-1 text-xs text-(--color-foreground-secondary)">
					结束日期
					<input
						aria-label="Model 重放结束日期"
						type="date"
						className={INPUT_CLASS}
						value={endDate}
						onChange={(event) => setEndDate(event.currentTarget.value)}
					/>
				</label>
				<label className="flex flex-col gap-1 text-xs text-(--color-foreground-secondary)">
					初始资本（CNY）
					<input
						aria-label="Model 初始资本"
						inputMode="decimal"
						className={INPUT_CLASS}
						value={initialCapital}
						onChange={(event) => setInitialCapital(event.currentTarget.value)}
					/>
				</label>
				<label className="flex flex-col gap-1 text-xs text-(--color-foreground-secondary)">
					知识/发布截止
					<input
						aria-label="Model 知识截止"
						className={INPUT_CLASS}
						value={cutoff}
						onChange={(event) => setCutoff(event.currentTarget.value)}
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
								strategy_id: strategyId,
								start_date: startDate,
								end_date: endDate,
								initial_capital: capital.toFixed(2),
								knowledge_cutoff: cutoff,
								publication_cutoff: cutoff,
								...(artifactIds.length > 0 ? { artifact_ids: artifactIds } : {}),
							});
						}}
					>
						重放目标
					</button>
				</div>
			</div>
			<label className="flex flex-col gap-1 px-4 pb-3 text-xs text-(--color-foreground-secondary)">
				钉住工件（可选，逗号分隔；留空解析当前可见目标）
				<input
					aria-label="Model 钉住工件"
					className={INPUT_CLASS}
					placeholder="signal-package-…"
					value={artifactIdsText}
					onChange={(event) => setArtifactIdsText(event.currentTarget.value)}
				/>
			</label>
			{identity === null && (
				<p className="px-4 pb-4 text-xs text-(--color-foreground-tertiary)">
					填写区间与初始资本后重放；响应会带回解析到的工件清单，可用于钉住重放旧身份。
				</p>
			)}
			{historyQuery.isError && (
				<div
					role="alert"
					className="mx-4 mb-4 flex items-center justify-between rounded-(--radius-sm) border border-(--color-risk-critical-fg) px-3 py-2 text-xs"
				>
					<span>Model 历史重放失败：{String(historyQuery.error)}</span>
					<button type="button" className="underline" onClick={() => void historyQuery.refetch()}>
						重试
					</button>
				</div>
			)}
			{historyQuery.data && (
				<div className="grid gap-3 border-t border-(--color-border-subtle) px-4 py-4">
					<div className="grid gap-2 md:grid-cols-2 xl:grid-cols-4">
						{historyQuery.data.targets.map((target) => (
							<div
								key={target.artifact_id}
								className="rounded-(--radius-sm) border border-(--color-border-subtle) bg-(--color-surface-strip) px-3 py-2"
							>
								<p className="text-[11px] text-(--color-foreground-tertiary)">{target.signal_date} 的保存目标</p>
								<p className="mt-1 break-all font-data text-xs text-(--color-foreground-secondary)">
									{target.artifact_id}
								</p>
							</div>
						))}
						{historyQuery.data.targets.length === 0 && (
							<p className="text-xs text-(--color-foreground-tertiary)">
								区间内没有可见的保存目标，无可重放历史（{historyQuery.data.empty_reason ?? "no_targets"}）。
							</p>
						)}
					</div>
					<AccountHistoryResult history={historyQuery.data} />
				</div>
			)}
		</section>
	);
}
