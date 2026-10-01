import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Panel, PanelBody, PanelHeader } from "@/features/shell";
import { ContextActions } from "@/providers";
import {
	type CreateResearchCaseBody,
	createResearchCase,
	type SelectionRun,
	type SelectionRunDiff,
	selectionKeys,
} from "../api";
import { toResearchCaseView } from "../research-case";

function compactIdentity(value: string): string {
	const [, digest] = value.split(":sha256:");
	return digest ? `${value.slice(0, value.indexOf(":sha256:"))} · ${digest.slice(0, 10)}` : value;
}

function truthLabel(value: boolean, yes: string, no: string): string {
	return value ? yes : no;
}

function ResearchCaseCreation({ run }: { readonly run: SelectionRun }) {
	const [objective, setObjective] = useState("");
	const [excluded, setExcluded] = useState<readonly number[]>([]);
	const [copied, setCopied] = useState(false);
	const createCase = useMutation({
		mutationKey: selectionKeys.researchCases(run.run_id),
		mutationFn: async (body: CreateResearchCaseBody) =>
			toResearchCaseView(await createResearchCase(run.run_id, body), run),
		onMutate: () => setCopied(false),
	});
	const view = createCase.data;
	const selectedIds = run.candidates
		.filter((candidate) => !excluded.includes(candidate.instrument_id))
		.map((candidate) => candidate.instrument_id);
	const canSubmit = objective.trim().length > 0 && (run.candidates.length === 0 || selectedIds.length > 0);

	async function copyCaseId(): Promise<void> {
		if (!view) return;
		await navigator.clipboard.writeText(view.caseId);
		setCopied(true);
	}

	return (
		<div className="mt-2 space-y-3 text-xs">
			{run.candidates.length > 0 && (
				<fieldset disabled={createCase.isPending} className="space-y-1">
					<legend className="text-(--color-foreground-tertiary)">
						候选范围（默认全部 {run.candidates.length} 只入选）
					</legend>
					<ul className="grid gap-1 sm:grid-cols-2">
						{run.candidates.map((candidate) => (
							<li key={candidate.instrument_id}>
								<label className="flex items-center gap-2">
									<input
										type="checkbox"
										aria-label={`纳入 ${candidate.instrument_id} ${candidate.instrument_name}`}
										checked={!excluded.includes(candidate.instrument_id)}
										onChange={() =>
											setExcluded((current) =>
												current.includes(candidate.instrument_id)
													? current.filter((value) => value !== candidate.instrument_id)
													: [...current, candidate.instrument_id],
											)
										}
									/>
									<span>
										<span className="font-mono">{candidate.instrument_id}</span> · {candidate.instrument_name}
									</span>
								</label>
							</li>
						))}
					</ul>
				</fieldset>
			)}
			<label className="grid gap-1">
				研究假设 objective
				<input
					aria-label="研究假设 objective"
					className="rounded-(--radius-sm) border border-(--color-border-primary) bg-(--color-surface-1) px-2 py-1.5 text-xs text-(--color-foreground)"
					disabled={createCase.isPending}
					placeholder="该运行要验证什么假设？"
					value={objective}
					onChange={(event) => setObjective(event.currentTarget.value)}
				/>
			</label>
			<div className="flex items-center gap-2">
				<Button
					type="button"
					disabled={createCase.isPending || !canSubmit}
					onClick={() => createCase.mutate({ candidate_instrument_ids: selectedIds, objective: objective.trim() })}
				>
					{createCase.isPending ? "创建中…" : "创建研究用例"}
				</Button>
				{view && (
					<Button type="button" variant="outline" onClick={() => void copyCaseId()}>
						{copied ? "已复制" : "复制用例 ID"}
					</Button>
				)}
			</div>
			{createCase.isError && (
				<p role="alert" className="text-(--color-risk-critical-fg)">
					{createCase.error.message}
				</p>
			)}
			{view && (
				<p
					role="status"
					className="break-all rounded-(--radius-sm) border border-(--color-border-subtle) bg-(--color-surface-1) p-2"
				>
					<span className="font-mono">{view.caseId}</span>
					<span className="ml-2 text-(--color-foreground-tertiary)">
						{view.degraded ? `降级 · 缺输入：${view.missingInputs || "未声明"}` : "就绪"}
					</span>
				</p>
			)}
		</div>
	);
}

export function SelectionRunDetail({
	diff,
	run,
}: {
	readonly diff: SelectionRunDiff | null;
	readonly run: SelectionRun | null;
}) {
	return (
		<Panel className="m-4 ml-0 h-[calc(100%-2rem)]" data-info-level="l2" data-info-unit="selection-detail">
			<PanelHeader
				title="SelectionRun 证据"
				subtitle={run ? `${run.asset_kind} · ${run.status}` : "exact run required"}
			/>
			<PanelBody className="space-y-5 overflow-y-auto p-4">
				{run ? (
					<>
						<section aria-label="运行身份" className="space-y-2">
							<p className="font-mono text-xs text-(--color-foreground-secondary)">{compactIdentity(run.run_id)}</p>
							<dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs">
								<dt className="text-(--color-foreground-tertiary)">as of</dt>
								<dd>{new Date(run.as_of).toLocaleString("zh-CN")}</dd>
								<dt className="text-(--color-foreground-tertiary)">spec</dt>
								<dd>
									{run.spec_id} · v{run.spec_version}
								</dd>
								<dt className="text-(--color-foreground-tertiary)">seed</dt>
								<dd className="font-mono">{run.seed}</dd>
								<dt className="text-(--color-foreground-tertiary)">universe</dt>
								<dd className="break-all font-mono">{run.universe_snapshot_id}</dd>
							</dl>
						</section>

						<section aria-labelledby="selection-lineage" className="border-t border-(--color-border-subtle) pt-4">
							<h3
								id="selection-lineage"
								className="text-xs font-semibold tracking-wide text-(--color-foreground-secondary)"
							>
								LINEAGE
							</h3>
							<ul className="mt-2 space-y-1 font-mono text-[11px] text-(--color-foreground-tertiary)">
								{run.source_snapshot_ids.map((snapshotId) => (
									<li key={snapshotId} className="break-all">
										{snapshotId}
									</li>
								))}
							</ul>
						</section>

						<section aria-labelledby="selection-next-actions" className="border-t border-(--color-border-subtle) pt-4">
							<h3
								id="selection-next-actions"
								className="text-xs font-semibold tracking-wide text-(--color-foreground-secondary)"
							>
								下游动作
							</h3>
							<div className="mt-2 grid grid-cols-2 gap-2 text-xs">
								<a
									className="rounded-(--radius-sm) border border-(--color-border-subtle) p-2 hover:bg-(--color-interaction-hover-subtle-bg)"
									href={`/research/universes?selectionRunId=${encodeURIComponent(run.run_id)}`}
								>
									Research
								</a>
								<a
									className="rounded-(--radius-sm) border border-(--color-border-subtle) p-2 hover:bg-(--color-interaction-hover-subtle-bg)"
									href={`/markets/watchlist?selectionRunId=${encodeURIComponent(run.run_id)}`}
								>
									Watchlist
								</a>
								<a
									className="rounded-(--radius-sm) border border-(--color-border-subtle) p-2 hover:bg-(--color-interaction-hover-subtle-bg)"
									href={`/portfolio/model?selectionRunId=${encodeURIComponent(run.run_id)}`}
								>
									Model
								</a>
								<a
									className="rounded-(--radius-sm) border border-(--color-border-subtle) p-2 hover:bg-(--color-interaction-hover-subtle-bg)"
									href={`/portfolio/paper?selectionRunId=${encodeURIComponent(run.run_id)}`}
								>
									Paper
								</a>
							</div>
						</section>

						<section aria-labelledby="selection-research-case" className="border-t border-(--color-border-subtle) pt-4">
							<h3
								id="selection-research-case"
								className="text-xs font-semibold tracking-wide text-(--color-foreground-secondary)"
							>
								创建研究用例
							</h3>
							<ResearchCaseCreation key={run.run_id} run={run} />
						</section>

						<section aria-labelledby="selection-agent" className="border-t border-(--color-border-subtle) pt-4">
							<h3
								id="selection-agent"
								className="text-xs font-semibold tracking-wide text-(--color-foreground-secondary)"
							>
								AGENT SIDECAR
							</h3>
							<p className="my-2 text-xs leading-5 text-(--color-foreground-tertiary)">
								Agent 只能引用该 run 的精确排名、排除原因和 evidence；不能新增候选。
							</p>
							<ContextActions
								contextId={run.run_id}
								contextType="selection"
								evidenceLabel="生成 SelectionMemo"
								evidenceObjective="生成 SelectionMemo"
							/>
						</section>
					</>
				) : (
					<p className="text-sm text-(--color-foreground-tertiary)">选择一个已保存运行查看精确证据。</p>
				)}

				{diff && (
					<section aria-labelledby="selection-diff" className="border-t border-(--color-border-subtle) pt-4">
						<h3 id="selection-diff" className="text-xs font-semibold tracking-wide text-(--color-foreground-secondary)">
							运行差异
						</h3>
						<div className="mt-2 grid gap-2 text-xs">
							<p>{truthLabel(diff.data_changed, "数据快照已变化", "数据快照未变化")}</p>
							<p>{truthLabel(diff.industry_rotation_changed, "行业轮动已变化", "行业轮动未变化")}</p>
							<p>{truthLabel(diff.spec_changed, "SelectionSpec 已变化", "SelectionSpec 未变化")}</p>
							{diff.rank_changes.map((change) => (
								<p key={change.instrument_id} className="font-mono">
									{change.instrument_id} · {change.before_rank} → {change.after_rank}
								</p>
							))}
						</div>
					</section>
				)}
			</PanelBody>
		</Panel>
	);
}
