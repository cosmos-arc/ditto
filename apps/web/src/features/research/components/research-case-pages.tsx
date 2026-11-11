import { useQuery } from "@tanstack/react-query";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { StatusBadge } from "@/components/status";
import { CatalogLayout, Panel, PanelBody, PanelHeader } from "@/features/shell";
import { ErrorState } from "@/lib/error-boundary";
import { sessionCalendarDate } from "@/lib/iso-calendar-date";
import {
	fetchResearchCaseDetail,
	fetchResearchCaseRun,
	fetchResearchCaseSummaries,
	type ResearchCaseDetail,
	researchCaseKeys,
} from "../api/research-cases";

function shortCaseId(value: string): string {
	return value.split(":sha256:").at(-1)?.slice(0, 12) ?? value;
}

function shortRunId(value: string): string {
	return value.split(":sha256:").at(-1)?.slice(0, 12) ?? value;
}

function formatInstant(value: string): string {
	return new Date(value).toLocaleString("zh-CN", { hour12: false });
}

/** 研究用例列表：从筛选交接来的持久化假设与候选范围（重开入口）。 */
export function ResearchCaseListPage() {
	const cases = useQuery({
		queryKey: researchCaseKeys.list,
		queryFn: () => fetchResearchCaseSummaries(),
		staleTime: 30_000,
	});

	return (
		<CatalogLayout
			toolbar={
				<div
					data-info-level="l1"
					data-info-unit="research-case-toolbar"
					className="flex flex-wrap items-end gap-3 border-b border-(--color-border-subtle) bg-(--color-surface-strip) px-4 py-2"
				>
					<div className="mr-auto">
						<p className="text-[11px] font-semibold tracking-[0.16em] text-(--color-accent)">RESEARCH CASES</p>
						<p className="text-xs text-(--color-foreground-tertiary)">
							从 SelectionRun 交接的持久化研究用例，重开不依赖创建时的页面
						</p>
					</div>
					<span className="text-xs text-(--color-foreground-tertiary)">
						{cases.data?.length ?? 0} {cases.data?.length === 1 ? "case" : "cases"}
					</span>
				</div>
			}
			main={
				<div data-info-level="l1" data-info-unit="research-case-list" className="h-full overflow-y-auto p-4">
					{cases.isLoading && <LoadingSkeleton variant="table" rows={4} />}
					{cases.isError && <ErrorState onRetry={() => void cases.refetch()} />}
					{cases.data?.length === 0 && (
						<div className="mx-auto max-w-lg py-12 text-center text-sm text-(--color-foreground-tertiary)">
							<p>尚无研究用例。在 Selection Workspace 的固定运行上创建研究用例后，会在这里持久保留目标与证据。</p>
							<a
								className="mt-3 inline-block rounded-(--radius-sm) border border-(--color-border-subtle) px-3 py-1.5 text-xs hover:bg-(--color-interaction-hover-subtle-bg)"
								href="/markets/screener"
							>
								前往 Selection Workspace
							</a>
						</div>
					)}
					{cases.data && cases.data.length > 0 && (
						<div className="overflow-x-auto rounded-(--radius-md) border border-(--color-border-subtle)">
							<table className="w-full text-left text-xs">
								<thead className="bg-(--color-surface-strip) text-(--color-foreground-tertiary)">
									<tr>
										<th className="px-3 py-2">用例</th>
										<th className="px-3 py-2">研究目标</th>
										<th className="px-3 py-2">来源运行</th>
										<th className="px-3 py-2">决策时点</th>
										<th className="px-3 py-2">候选</th>
										<th className="px-3 py-2">状态</th>
									</tr>
								</thead>
								<tbody className="divide-y divide-(--color-border-subtle)">
									{cases.data.map((item) => (
										<tr key={item.case_id} data-info-level="l3" data-info-unit="research-case-row">
											<td className="px-3 py-3 font-mono">{shortCaseId(item.case_id)}</td>
											<td className="max-w-96 px-3 py-3">
												<a
													className="font-medium hover:text-(--color-accent)"
													href={`/research/cases/${encodeURIComponent(item.case_id)}`}
												>
													{item.objective}
												</a>
												<span className="mt-1 block break-all font-mono text-[11px] text-(--color-foreground-tertiary)">
													{item.case_id}
												</span>
											</td>
											<td className="px-3 py-3 font-mono text-[11px] text-(--color-foreground-tertiary)">
												{shortRunId(item.selection_run_id)}
											</td>
											<td className="px-3 py-3 font-mono">{formatInstant(item.as_of)}</td>
											<td className="px-3 py-3">{item.candidate_count} 只候选</td>
											<td className="px-3 py-3">
												<StatusBadge
													label={item.selection_status.toUpperCase()}
													size="sm"
													variant={item.selection_status === "ready" ? "healthy" : "warning"}
												/>
											</td>
										</tr>
									))}
								</tbody>
							</table>
						</div>
					)}
				</div>
			}
			detail={
				<Panel className="m-4 ml-0 h-[calc(100%-2rem)]" data-info-level="l2" data-info-unit="research-case-guide">
					<PanelHeader title="研究用例" subtitle="persisted handoffs" />
					<PanelBody className="space-y-3 p-4 text-xs text-(--color-foreground-tertiary)">
						<p>每条用例绑定一次固定 SelectionRun：目标、候选范围、时间身份与来源快照在创建时冻结。</p>
						<p>后续新增数据或修订不会改写已交接的证据；继续研究会得到新的运行与新的用例。</p>
					</PanelBody>
				</Panel>
			}
		/>
	);
}

function TemporalIdentity({ value }: { readonly value: ResearchCaseDetail }) {
	return (
		<section aria-label="时间身份">
			<dl className="grid grid-cols-[7rem_1fr] gap-x-3 gap-y-1 text-xs">
				<dt className="text-(--color-foreground-tertiary)">as of</dt>
				<dd className="font-mono">{formatInstant(value.as_of)}</dd>
				<dt className="text-(--color-foreground-tertiary)">knowledge cutoff</dt>
				<dd className="font-mono">{formatInstant(value.knowledge_cutoff)}</dd>
				<dt className="text-(--color-foreground-tertiary)">publication cutoff</dt>
				<dd className="font-mono">{formatInstant(value.publication_cutoff)}</dd>
			</dl>
		</section>
	);
}

/** 单条研究用例详情：重开交接时的目标、日期、来源与候选选择。 */
export function ResearchCaseDetailPage({ caseId }: { readonly caseId: string }) {
	const detail = useQuery({
		queryKey: researchCaseKeys.detail(caseId),
		queryFn: () => fetchResearchCaseDetail(caseId),
		staleTime: Number.POSITIVE_INFINITY,
		retry: false,
	});
	const run = useQuery({
		queryKey: researchCaseKeys.run(detail.data?.selection_run_id ?? "none"),
		queryFn: () => fetchResearchCaseRun(detail.data?.selection_run_id ?? ""),
		enabled: detail.data !== undefined,
		staleTime: Number.POSITIVE_INFINITY,
		retry: false,
	});

	if (detail.isLoading) return <LoadingSkeleton variant="panel" rows={8} />;
	if (detail.isError || !detail.data) {
		return (
			<div className="grid min-h-80 place-items-center p-8">
				<div className="max-w-lg border-l-2 border-(--color-risk-warning-fg) pl-5">
					<p className="text-sm font-semibold text-(--color-foreground)">未找到该研究用例</p>
					<p className="mt-2 break-all font-mono text-xs text-(--color-foreground-tertiary)">{caseId}</p>
					<p className="mt-2 text-xs leading-5 text-(--color-foreground-tertiary)">
						用例只在创建时持久化一次；该链接可能指向从未创建的用例。不会替换为其他用例。
					</p>
					<a
						className="mt-3 inline-block rounded-(--radius-sm) border border-(--color-border-subtle) px-3 py-1.5 text-xs hover:bg-(--color-interaction-hover-subtle-bg)"
						href="/research/cases"
					>
						回到研究用例列表
					</a>
				</div>
			</div>
		);
	}

	const value = detail.data;
	const observeDate = sessionCalendarDate(value.as_of);
	const runCandidates = run.data?.candidates ?? [];
	const roster = value.candidate_instrument_ids
		.map((instrumentId) => runCandidates.find((item) => item.instrument_id === instrumentId))
		.map((candidate, index) => ({ candidate, instrumentId: value.candidate_instrument_ids[index] as number }));
	// 候选下钻与观察日入口共用同一锚定合同（图表截至日=用例观察日）。
	const rosterHref = (instrumentId: number) =>
		`/instruments/${instrumentId}?tab=chart${observeDate ? `&observeDate=${observeDate}` : ""}&selectionRunId=${encodeURIComponent(value.selection_run_id)}`;
	const firstRosterEntry = roster.find((item) => item.candidate);

	return (
		<div className="h-full overflow-y-auto bg-(--color-surface-0) p-3 text-sm">
			<div className="mx-auto grid max-w-[1500px] gap-3 xl:grid-cols-[minmax(0,1fr)_22rem]">
				<main className="min-w-0 space-y-3">
					<section
						className="border border-(--color-border-subtle) bg-(--color-surface-panel-base) px-4 py-3"
						data-info-level="l2"
						data-info-unit="research-case-header"
					>
						<div className="flex flex-wrap items-start justify-between gap-3">
							<div className="min-w-0">
								<p className="text-[11px] font-semibold tracking-[0.16em] text-(--color-accent)">RESEARCH CASE</p>
								<h2 className="mt-1 text-base font-semibold">{value.objective}</h2>
							</div>
							<StatusBadge
								label={value.selection_status.toUpperCase()}
								size="sm"
								variant={value.selection_status === "ready" ? "healthy" : "warning"}
							/>
						</div>
						<section
							aria-label="用例身份"
							className="mt-2 space-y-1 font-mono text-[11px] text-(--color-foreground-tertiary)"
						>
							<p className="break-all">{value.case_id}</p>
							<p className="break-all">{value.selection_run_id}</p>
						</section>
					</section>

					<section
						className="border border-(--color-border-subtle) bg-(--color-surface-panel-base) px-4 py-3"
						data-info-level="l2"
						data-info-unit="research-case-roster"
						aria-label="候选名单"
					>
						<div className="mb-2 flex items-center justify-between">
							<h3 className="text-sm font-semibold">候选名单（{value.candidate_instrument_ids.length} 只）</h3>
							{observeDate &&
								(firstRosterEntry ? (
									// 观察日入口与候选行同语言（视觉门 V2'）：强调色 + hover
									// 下划线，点击按该观察日打开首席选图表（真实锚定动作）。
									<a
										aria-label={`按观察日 ${observeDate} 打开首席选图表`}
										className="text-xs font-medium text-(--color-accent) hover:underline"
										href={rosterHref(firstRosterEntry.instrumentId)}
									>
										观察日 {observeDate} ↗
									</a>
								) : (
									<span className="text-xs text-(--color-foreground-tertiary)">观察日 {observeDate}</span>
								))}
						</div>
						{run.isLoading && <LoadingSkeleton variant="table" rows={3} />}
						{run.isError && (
							<p className="text-xs text-(--color-risk-warning-fg)">
								来源运行暂不可读，候选只显示固定身份：{value.candidate_instrument_ids.join("、")}
							</p>
						)}
						{run.data && roster.length > 0 && (
							<table className="w-full text-left text-xs">
								<thead className="text-(--color-foreground-tertiary)">
									<tr>
										<th className="px-2 py-1.5">Rank</th>
										<th className="px-2 py-1.5">标的</th>
										<th className="px-2 py-1.5">Score</th>
									</tr>
								</thead>
								<tbody className="divide-y divide-(--color-border-subtle)">
									{roster.map(({ candidate, instrumentId }) => (
										<tr key={instrumentId}>
											<td className="px-2 py-2 font-mono">#{candidate?.rank ?? "—"}</td>
											<td className="px-2 py-2">
												{/* 下钻可供性与域内比较入口同语言：强调色 + hover 下划线。 */}
												<a
													className="font-medium text-(--color-accent) hover:underline"
													href={rosterHref(instrumentId)}
												>
													{candidate?.instrument_name ?? "来源运行未含该候选"}
												</a>
												<span className="ml-2 font-mono text-[11px] text-(--color-foreground-tertiary)">
													{instrumentId}
												</span>
											</td>
											<td className="px-2 py-2 font-mono">{candidate ? candidate.score.toFixed(4) : "—"}</td>
										</tr>
									))}
								</tbody>
							</table>
						)}
					</section>
				</main>

				<aside className="min-w-0 space-y-3" data-info-level="l2" data-info-unit="research-case-inspector">
					<Panel>
						<PanelHeader title="时间身份" subtitle="frozen at handoff" />
						<PanelBody className="p-4">
							<TemporalIdentity value={value} />
						</PanelBody>
					</Panel>
					<Panel>
						<PanelHeader title="来源" subtitle="exact lineage" />
						<PanelBody className="space-y-2 p-4 text-[11px]">
							<p className="break-all font-mono text-(--color-foreground-tertiary)">{value.universe_snapshot_id}</p>
							<ul className="space-y-1 font-mono text-(--color-foreground-tertiary)">
								{value.source_snapshot_ids.map((snapshotId) => (
									<li key={snapshotId} className="break-all">
										{snapshotId}
									</li>
								))}
							</ul>
							{value.missing_inputs.length > 0 && (
								<p className="text-(--color-risk-warning-fg)">缺输入：{value.missing_inputs.join("、")}</p>
							)}
						</PanelBody>
					</Panel>
					<Panel>
						<PanelHeader title="继续研究" subtitle="non-agent handoff" />
						<PanelBody className="space-y-2 p-4 text-xs">
							<a
								className="block rounded-(--radius-sm) border border-(--color-border-subtle) p-2 hover:bg-(--color-interaction-hover-subtle-bg)"
								href={`/markets/screener?run=${encodeURIComponent(value.selection_run_id)}&spec=${encodeURIComponent(run.data?.spec_id ?? "")}`}
							>
								回到该运行的筛选工作面
							</a>
							<p className="text-(--color-foreground-tertiary)">
								筛选工作面会按该固定运行恢复候选/排除与运行历史；不需要 Agent 或复制内部 ID。
							</p>
						</PanelBody>
					</Panel>
				</aside>
			</div>
		</div>
	);
}
