import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { fetchNextDayPlan, listNextDayPlans, type NextDayPlanSummary, recordNextDayPlan } from "../api/next-day-plans";
import type { WatchlistEntryFn } from "./market-view-contracts";

type Props = {
	/** 自选对象身份：候选勾选与已存计划的业务代码解析都从这里出发。 */
	readonly ids: readonly number[];
	/** 单对象精确身份解析（#738 合同）：解析失败的对象保留内部 ID 标注。 */
	readonly resolveEntry: WatchlistEntryFn;
	/** 最近完整交易日锚点（#739 合同）；未落定时为 null，表单等待手填日期。 */
	readonly defaultObservationDate: string | null;
};

const PLANS_KEY = ["next-day-plans"] as const;

export function NextDayPlanPanel({ ids, resolveEntry, defaultObservationDate }: Props) {
	const queryClient = useQueryClient();
	const [selected, setSelected] = useState<number[]>([]);
	const [reasons, setReasons] = useState<Record<number, string>>({});
	const [planText, setPlanText] = useState("");
	// 锚点异步落定：只在用户尚未手填时回填默认观察日期（手填优先）。
	const [observationDate, setObservationDate] = useState(defaultObservationDate ?? "");
	const [dateTouched, setDateTouched] = useState(false);
	useEffect(() => {
		if (!dateTouched && defaultObservationDate) setObservationDate(defaultObservationDate);
	}, [defaultObservationDate, dateTouched]);
	const plans = useQuery({ queryKey: PLANS_KEY, queryFn: () => listNextDayPlans() });
	const save = useMutation({
		mutationFn: () =>
			recordNextDayPlan({
				observationDate,
				candidateNotes: selected.map((id) => ({
					instrumentId: id,
					reason: reasons[id] ?? "",
				})),
				nextDayPlan: planText,
			}),
		onSuccess: () => {
			void queryClient.invalidateQueries({ queryKey: PLANS_KEY });
		},
	});
	const canSave =
		/^\d{4}-\d{2}-\d{2}$/u.test(observationDate) &&
		selected.length > 0 &&
		selected.every((id) => (reasons[id] ?? "").trim().length > 0) &&
		planText.trim().length > 0 &&
		!save.isPending;
	return (
		<section aria-label="候选理由与次日计划" className="space-y-3">
			<h3 className="font-medium">候选理由与次日计划</h3>
			<p className="text-(--color-foreground-tertiary)">
				保存盘后判断：每个候选一条理由，加上次日要执行的计划。记录绑定自己的观察日期，重开不随页面日期改写。
			</p>
			<fieldset>
				<legend>本次候选（来自自选）</legend>
				{ids.length === 0 && <p>自选为空；先检索并加入自选对象。</p>}
				{ids.map((id) => (
					<PlanCandidateRow
						key={id}
						instrumentId={id}
						resolveEntry={resolveEntry}
						checked={selected.includes(id)}
						reason={reasons[id] ?? ""}
						onToggle={(next) =>
							setSelected((current) => (next ? [...current, id] : current.filter((item) => item !== id)))
						}
						onReason={(value) => setReasons((current) => ({ ...current, [id]: value }))}
					/>
				))}
			</fieldset>
			<label className="block">
				观察日期{" "}
				<input
					aria-label="观察日期"
					type="date"
					value={observationDate}
					onChange={(event) => {
						setDateTouched(true);
						setObservationDate(event.target.value);
					}}
				/>
			</label>
			{defaultObservationDate === null && (
				<p className="text-(--color-foreground-tertiary)">最近完整交易日尚未落定；手填观察日期后可保存。</p>
			)}
			<label className="block">
				次日计划{" "}
				<textarea
					aria-label="次日计划"
					rows={3}
					value={planText}
					onChange={(event) => setPlanText(event.target.value)}
					placeholder="明天开盘要验证什么、执行什么"
				/>
			</label>
			<button type="button" disabled={!canSave} onClick={() => save.mutate()}>
				{save.isPending ? "保存中…" : "保存理由与次日计划"}
			</button>
			{save.isError && <p role="alert">保存失败：{String(save.error)}；草稿已保留，可重试。</p>}
			{save.isSuccess && (
				<p className="break-all">
					已保存 {save.data.planId}（观察日 {save.data.observationDate}）。
				</p>
			)}
			<PlansList
				plans={plans.data ?? []}
				plansError={plans.isError}
				onRetry={() => void plans.refetch()}
				resolveEntry={resolveEntry}
			/>
		</section>
	);
}

function PlanCandidateRow({
	instrumentId,
	resolveEntry,
	checked,
	reason,
	onToggle,
	onReason,
}: {
	readonly instrumentId: number;
	readonly resolveEntry: WatchlistEntryFn;
	readonly checked: boolean;
	readonly reason: string;
	readonly onToggle: (next: boolean) => void;
	readonly onReason: (value: string) => void;
}) {
	const identity = useQuery({
		queryKey: ["plan-entry-instrument", instrumentId],
		queryFn: () => resolveEntry(instrumentId),
		staleTime: 60_000,
		retry: false,
	});
	const label = identity.data ? `${identity.data.ticker} ${identity.data.name}` : `#${instrumentId}`;
	return (
		<div className="space-y-1">
			<label className="block">
				<input type="checkbox" checked={checked} onChange={(event) => onToggle(event.target.checked)} /> {label}
			</label>
			{checked && (
				<label className="block">
					{identity.data ? identity.data.ticker : instrumentId} 候选理由{" "}
					<input
						aria-label={`${identity.data ? identity.data.ticker : instrumentId} 候选理由`}
						value={reason}
						onChange={(event) => onReason(event.target.value)}
						placeholder="为什么它留在明天的名单上"
					/>
				</label>
			)}
		</div>
	);
}

function PlansList({
	plans,
	plansError,
	onRetry,
	resolveEntry,
}: {
	readonly plans: readonly NextDayPlanSummary[];
	readonly plansError: boolean;
	readonly onRetry: () => void;
	readonly resolveEntry: WatchlistEntryFn;
}) {
	return (
		<section aria-label="已保存理由与次日计划" className="space-y-2">
			<h4>已保存记录</h4>
			{plansError && (
				<button type="button" onClick={onRetry}>
					记录读取失败，重试
				</button>
			)}
			{!plansError && plans.length === 0 && <p>还没有保存过的理由与计划。</p>}
			{plans.map((item) => (
				<PlanEntry key={item.planId} summary={item} resolveEntry={resolveEntry} />
			))}
		</section>
	);
}

function PlanEntry({
	summary,
	resolveEntry,
}: {
	readonly summary: NextDayPlanSummary;
	readonly resolveEntry: WatchlistEntryFn;
}) {
	const [open, setOpen] = useState(false);
	const detail = useQuery({
		queryKey: ["next-day-plan", summary.planId],
		queryFn: () => fetchNextDayPlan(summary.planId),
		enabled: open,
		retry: false,
	});
	return (
		<div className="rounded border border-(--color-border-subtle) p-2">
			<p>
				观察日 {summary.observationDate} · {summary.candidateCount} 个候选 · 记录于 {summary.createdAt}
			</p>
			<p className="text-(--color-foreground-tertiary)">{summary.nextDayPlan}</p>
			<button type="button" onClick={() => setOpen((current) => !current)}>
				{open ? "收起计划原文" : "展开计划原文"}
			</button>
			{open && detail.isError && (
				<p role="alert">
					原文读取失败：{String(detail.error)}
					<button type="button" onClick={() => void detail.refetch()}>
						重试
					</button>
				</p>
			)}
			{open && detail.data && (
				<ul>
					{detail.data.candidateNotes.map((note) => (
						<PlanNoteLine
							key={note.instrumentId}
							instrumentId={note.instrumentId}
							reason={note.reason}
							resolveEntry={resolveEntry}
						/>
					))}
				</ul>
			)}
		</div>
	);
}

function PlanNoteLine({
	instrumentId,
	reason,
	resolveEntry,
}: {
	readonly instrumentId: number;
	readonly reason: string;
	readonly resolveEntry: WatchlistEntryFn;
}) {
	const identity = useQuery({
		queryKey: ["plan-entry-instrument", instrumentId],
		queryFn: () => resolveEntry(instrumentId),
		staleTime: 60_000,
		retry: false,
	});
	return <li>{`${identity.data ? identity.data.ticker : `#${instrumentId}`}：${reason}`}</li>;
}
