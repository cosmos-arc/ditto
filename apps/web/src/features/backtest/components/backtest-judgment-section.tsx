import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { listResearchJudgments, type ResearchJudgmentSummary, recordResearchJudgment } from "../api/research-judgments";
import type { BacktestRun } from "../types";

/**
 * 比较视图的「研究判断」区（#748）。
 *
 * - 保存的判断绑定明确的比较成员 run_ids（会话选择序原样冻结），append-only
 *   内容寻址：重开找回原结果，后续新数据不改写已存结论；
 * - 可选绑定后续验证策略@版本（选项=当前比较成员的 distinct
 *   strategyId@strategyVersion）：「进入验证」跳策略详情页（既有提交回测
 *   sheet 入口），页面带「返回研究判断」回程链接；
 * - 「转入次日计划」带 ?judgment= 参数进计划面板，保存的计划携带来源。
 */

const JUDGMENTS_KEY = ["research-judgments"] as const;
// 列表读取的显式请求量：返回条数达到该值时如实披露可能存在截断。
const JUDGMENTS_LIMIT = 20;

type Props = {
	/** 会话比较集合（判断绑定的明确运行身份，选择序原样冻结）。 */
	readonly runIds: readonly string[];
	/** 已读取的比较成员 run（后续验证策略选项来源）。 */
	readonly runs: readonly BacktestRun[];
};

export function BacktestJudgmentSection({ runIds, runs }: Props) {
	const queryClient = useQueryClient();
	const [judgmentText, setJudgmentText] = useState("");
	const [strategyKey, setStrategyKey] = useState("");
	// 选项 = 比较成员的 distinct strategyId@strategyVersion（展示顺序保持首次出现序）。
	const strategyOptions = useMemo(() => {
		const byKey = new Map<string, { strategyId: string; version: number }>();
		for (const run of runs) {
			const version = Number.parseInt(run.strategyVersion, 10);
			if (!Number.isInteger(version) || version < 1) continue;
			const key = `${run.strategyId}@${version}`;
			if (!byKey.has(key)) byKey.set(key, { strategyId: run.strategyId, version });
		}
		return [...byKey.entries()];
	}, [runs]);
	const selected = strategyOptions.find(([key]) => key === strategyKey);
	const save = useMutation({
		mutationFn: () =>
			recordResearchJudgment({
				runIds,
				judgment: judgmentText.trim(),
				...(selected ? { strategyId: selected[1].strategyId, strategyVersion: selected[1].version } : {}),
			}),
		onSuccess: () => {
			void queryClient.invalidateQueries({ queryKey: JUDGMENTS_KEY });
		},
	});
	const judgments = useQuery({
		queryKey: JUDGMENTS_KEY,
		queryFn: () => listResearchJudgments(JUDGMENTS_LIMIT),
	});
	const canSave = runIds.length > 0 && judgmentText.trim().length > 0 && !save.isPending;
	return (
		<section
			aria-label="研究判断"
			data-testid="research-judgment-section"
			className="flex flex-col gap-2 border-t border-(--color-border-subtle) pt-3"
		>
			<h4 className="text-xs font-semibold uppercase tracking-[0.08em] text-(--color-foreground-tertiary)">
				研究判断（绑定当前比较集合，保存后可重开）
			</h4>
			<p className="text-xs text-(--color-foreground-tertiary)">
				判断绑定明确 run 身份（{runIds.length > 0 ? runIds.join(" · ") : "尚未选择运行"}），append-only
				保存；后续新数据不改写已存结论。
			</p>
			<label className="block text-xs">
				判断结论{" "}
				<textarea
					aria-label="判断结论"
					data-testid="judgment-text"
					rows={2}
					value={judgmentText}
					onChange={(event) => setJudgmentText(event.target.value)}
					placeholder="这次比较的结论：为什么、下一步验证什么"
				/>
			</label>
			<label className="block text-xs">
				后续验证策略版本（可选）{" "}
				<select
					aria-label="后续验证策略版本"
					data-testid="judgment-strategy"
					value={strategyKey}
					onChange={(event) => setStrategyKey(event.target.value)}
				>
					<option value="">暂不指定</option>
					{strategyOptions.map(([key]) => (
						<option key={key} value={key}>
							{key}
						</option>
					))}
				</select>
			</label>
			<Button type="button" size="xs" variant="outline" disabled={!canSave} onClick={() => save.mutate()}>
				{save.isPending ? "保存中…" : "保存研究判断"}
			</Button>
			{save.isError && (
				<p role="alert" className="text-xs">
					保存失败：{String(save.error)}；草稿已保留，可重试。
				</p>
			)}
			{save.isSuccess && (
				<p className="break-all text-xs">
					已保存 <span className="font-mono">{save.data.judgmentId}</span>
				</p>
			)}
			<section aria-label="已保存研究判断" className="flex flex-col gap-2">
				{judgments.isError && (
					<button type="button" className="text-xs" onClick={() => void judgments.refetch()}>
						判断列表读取失败，重试
					</button>
				)}
				{!judgments.isError && (judgments.data ?? []).length === 0 && (
					<p className="text-xs text-(--color-foreground-tertiary)">还没有保存过的研究判断。</p>
				)}
				{(judgments.data ?? []).length >= JUDGMENTS_LIMIT && (
					<p data-testid="judgment-list-truncated" className="text-xs text-(--color-foreground-tertiary)">
						仅显示最近 {JUDGMENTS_LIMIT} 条
					</p>
				)}
				{(judgments.data ?? []).map((item) => (
					<JudgmentEntry key={item.judgmentId} summary={item} />
				))}
			</section>
		</section>
	);
}

function JudgmentEntry({ summary }: { readonly summary: ResearchJudgmentSummary }) {
	return (
		<div data-testid="research-judgment-entry" className="rounded border border-(--color-border-subtle) p-2 text-xs">
			<p className="break-all font-mono text-(--color-foreground-tertiary)">{summary.judgmentId}</p>
			<p className="text-(--color-foreground-secondary)">{summary.judgment}</p>
			<p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-(--color-foreground-tertiary)">
				{summary.runIds.map((runId) => (
					<a
						key={runId}
						href={`/research/backtests/${encodeURIComponent(runId)}`}
						className="break-all font-data text-(--color-accent) underline underline-offset-2"
					>
						{runId}
					</a>
				))}
				{summary.strategyId !== null && summary.strategyVersion !== null && (
					<a
						href={`/research/strategies/${encodeURIComponent(summary.strategyId)}?fromJudgment=${encodeURIComponent(summary.judgmentId)}`}
						className="font-medium text-(--color-accent) underline underline-offset-2"
					>
						进入验证 {summary.strategyId}@v{summary.strategyVersion}
					</a>
				)}
				<a
					href={`/markets/watchlist?judgment=${encodeURIComponent(summary.judgmentId)}`}
					className="font-medium text-(--color-accent) underline underline-offset-2"
				>
					转入次日计划
				</a>
			</p>
		</div>
	);
}
