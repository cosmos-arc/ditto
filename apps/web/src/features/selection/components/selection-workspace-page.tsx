import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { Button } from "@/components/ui/button";
import { CatalogLayout } from "@/features/shell";
import { ErrorState } from "@/lib/error-boundary";
import { sessionCalendarDate } from "@/lib/iso-calendar-date";
import { StaleIndicator } from "@/lib/stale-indicator";
import { compareSelectionRuns, createSelectionRun, getSelectionRun, listSelectionRuns, selectionKeys } from "../api";
import { SelectionRunDetail } from "./selection-run-detail";
import { SelectionRunInput } from "./selection-run-input";

type ResultsTab = "candidates" | "exclusions";

const DEFAULT_SELECTION_SPEC_ID = "a-share-stock-discovery";

function shortRunId(value: string): string {
	return value.split(":sha256:").at(-1)?.slice(0, 12) ?? value;
}

export function SelectionWorkspacePage({
	initialSpecId = DEFAULT_SELECTION_SPEC_ID,
	initialRunId,
	initialTab,
	onSpecIdChange,
	onRunIdChange,
	onTabChange,
}: {
	/** 从 URL/导航携带的 spec 身份：刷新或返回后恢复运行历史范围。 */
	readonly initialSpecId?: string | undefined;
	/** 从 URL/研究用例带回的固定运行身份：重开旧证据而不是自动选最新。 */
	readonly initialRunId?: string | undefined;
	/** 从 URL 恢复的结果视图（候选/排除）。 */
	readonly initialTab?: ResultsTab | undefined;
	readonly onSpecIdChange?: (specId: string) => void;
	readonly onRunIdChange?: (runId: string | undefined) => void;
	readonly onTabChange?: (tab: ResultsTab) => void;
}) {
	const queryClient = useQueryClient();
	const [specId, setSpecId] = useState(initialSpecId);
	const [selectedRunId, setSelectedRunId] = useState<string | null>(initialRunId ?? null);
	// 用户显式放弃固定运行（未找到）后回到自动选择，直到宿主给出新身份。
	const [dismissedRunId, setDismissedRunId] = useState<string | null>(null);
	const pinnedRunId = initialRunId !== undefined && initialRunId !== dismissedRunId ? initialRunId : undefined;
	// 同路由 search 变化（浏览器返回/前进、站内链接切换 ?spec=/?run=）不重挂载
	// 组件：受控跟随宿主传入的身份；用户清空输入框时宿主回 undefined，
	// 保留清空状态而不是重置回默认（issue 740 F4）。
	useEffect(() => {
		if (initialSpecId !== undefined) setSpecId(initialSpecId);
	}, [initialSpecId]);
	useEffect(() => {
		setSelectedRunId(initialRunId ?? null);
		if (initialRunId !== undefined) setDismissedRunId(null);
	}, [initialRunId]);
	const [compareIds, setCompareIds] = useState<readonly string[]>([]);
	const [tab, setTab] = useState<ResultsTab>(initialTab === "exclusions" ? "exclusions" : "candidates");
	useEffect(() => {
		setTab(initialTab === "exclusions" ? "exclusions" : "candidates");
	}, [initialTab]);
	const [feedback, setFeedback] = useState<string | null>(null);
	const normalizedSpecId = specId.trim();

	const history = useQuery({
		queryKey: selectionKeys.runs(normalizedSpecId),
		queryFn: () => listSelectionRuns(normalizedSpecId),
		enabled: normalizedSpecId.length > 0,
		staleTime: 30_000,
	});
	// 自动选中只在无固定运行时发生：URL 显式重开一条运行时，历史缺失或
	// GET 失败都保持诚实状态，绝不静默换成最新运行（旧证据不偷换）。
	useEffect(() => {
		if (pinnedRunId !== undefined) return;
		const first = history.data?.[0];
		if (first && !history.data?.some((run) => run.run_id === selectedRunId)) setSelectedRunId(first.run_id);
	}, [history.data, pinnedRunId, selectedRunId]);

	const exactRun = useQuery({
		queryKey: selectionKeys.run(selectedRunId ?? "none"),
		queryFn: () => getSelectionRun(selectedRunId ?? ""),
		enabled: selectedRunId !== null,
		staleTime: Number.POSITIVE_INFINITY,
	});
	// 重开一条固定运行时同步 spec 家族：历史与反馈跟随该运行的条件身份。
	useEffect(() => {
		const loadedSpec = exactRun.data?.spec_id;
		if (loadedSpec && loadedSpec !== specId) {
			setSpecId(loadedSpec);
			onSpecIdChange?.(loadedSpec);
		}
	}, [exactRun.data?.spec_id, onSpecIdChange, specId]);

	const comparison = useMutation({
		mutationFn: (ids: readonly [string, string]) => compareSelectionRuns(ids[0], ids[1]),
	});
	const createRun = useMutation({
		mutationFn: createSelectionRun,
		onSuccess: async (receipt) => {
			commitSpecId(receipt.selection_run.spec_id);
			commitRunId(receipt.selection_run.run_id);
			// 保存的条件（SelectionSpec，用户命名的可重跑身份）与固定结果
			// （SelectionRun，内容寻址身份）分别展示；live 车道的知识截止
			// 按发起时刻签发，重复提交各得一个固定身份。
			setFeedback(
				`已保存固定 SelectionRun ${shortRunId(receipt.selection_run.run_id)} · 可重跑条件 ${receipt.selection_run.spec_id}:${receipt.selection_run.spec_version}`,
			);
			queryClient.setQueryData(selectionKeys.run(receipt.selection_run.run_id), receipt.selection_run);
			await queryClient.invalidateQueries({ queryKey: selectionKeys.runs(receipt.selection_run.spec_id) });
		},
	});

	function commitSpecId(next: string): void {
		setSpecId(next);
		onSpecIdChange?.(next);
	}

	function commitRunId(next: string): void {
		setSelectedRunId(next);
		onRunIdChange?.(next);
	}

	function selectTab(next: ResultsTab): void {
		setTab(next);
		onTabChange?.(next);
	}

	function toggleCompare(runId: string): void {
		setCompareIds((current) => {
			if (current.includes(runId)) return current.filter((value) => value !== runId);
			return current.length >= 2 ? [current[1] as string, runId] : [...current, runId];
		});
		comparison.reset();
	}

	const run = exactRun.data ?? null;
	const currentItems = tab === "candidates" ? run?.candidates : run?.exclusions;
	const pinnedRunMissing = pinnedRunId !== undefined && exactRun.isError;
	// 观察日随运行决策时点冻结：下钻图表以此日为锚，重开旧运行仍是旧观察日。
	const runObserveDate = run ? sessionCalendarDate(run.as_of) : null;

	return (
		<CatalogLayout
			toolbar={
				<div
					data-info-level="l1"
					data-info-unit="selection-toolbar"
					className="flex flex-wrap items-end gap-3 border-b border-(--color-border-subtle) bg-(--color-surface-strip) px-4 py-2"
				>
					<div className="mr-auto">
						<p className="text-[11px] font-semibold tracking-[0.16em] text-(--color-accent)">SELECTION WORKSPACE</p>
						<p className="text-xs text-(--color-foreground-tertiary)">保存运行，而不是临时筛选条件</p>
					</div>
					<label className="grid gap-1 text-xs text-(--color-foreground-tertiary)">
						SelectionSpec ID
						<input
							aria-label="SelectionSpec ID"
							className="w-52 rounded-(--radius-sm) border border-(--color-border-primary) bg-(--color-surface-1) px-2 py-1.5 font-mono text-xs text-(--color-foreground)"
							value={specId}
							onChange={(event) => commitSpecId(event.currentTarget.value)}
						/>
					</label>
					<Button
						type="button"
						variant="outline"
						onClick={() => void history.refetch()}
						disabled={!normalizedSpecId || history.isFetching}
					>
						刷新历史
					</Button>
					<Button
						type="button"
						disabled={compareIds.length !== 2 || comparison.isPending}
						onClick={() =>
							compareIds.length === 2 && comparison.mutate([compareIds[1] as string, compareIds[0] as string])
						}
					>
						比较 {compareIds.length} 个运行
					</Button>
				</div>
			}
			main={
				<div data-info-level="l1" data-info-unit="selection-main" className="h-full overflow-y-auto">
					<StaleIndicator isStale={Boolean(history.data && history.isFetching)} />
					<SelectionRunInput busy={createRun.isPending} onRun={(input) => createRun.mutate(input)} />
					{feedback && (
						<p
							role="status"
							className="border-b border-(--color-border-subtle) px-4 py-2 text-xs text-(--color-system-healthy-fg)"
						>
							{feedback}
						</p>
					)}
					{createRun.isError && (
						<p role="alert" className="px-4 py-2 text-xs text-(--color-risk-critical-fg)">
							{createRun.error.message}
						</p>
					)}
					{pinnedRunMissing && pinnedRunId !== undefined && (
						<div role="alert" className="border-b border-(--color-border-subtle) px-4 py-3 text-xs leading-5">
							<p className="font-medium text-(--color-risk-critical-fg)">未找到该固定运行</p>
							<p className="mt-1 break-all font-mono text-(--color-foreground-tertiary)">{pinnedRunId}</p>
							<p className="mt-1 text-(--color-foreground-tertiary)">
								运行历史只保存已创建的固定结果；链接可能指向从未创建的运行，也可能是后端暂不可达。不会自动替换为最新运行。
							</p>
							<Button
								type="button"
								variant="outline"
								size="sm"
								className="mt-2"
								onClick={() => {
									setDismissedRunId(pinnedRunId);
									setSelectedRunId(null);
									onRunIdChange?.(undefined);
								}}
							>
								回到该 spec 最新运行
							</Button>
						</div>
					)}

					<section aria-labelledby="selection-history" className="border-b border-(--color-border-subtle) px-4 py-3">
						<div className="mb-2 flex items-center justify-between">
							<h2
								id="selection-history"
								className="text-xs font-semibold tracking-wide text-(--color-foreground-secondary)"
							>
								RUN HISTORY
							</h2>
							<span className="text-xs text-(--color-foreground-tertiary)">{history.data?.length ?? 0} runs</span>
						</div>
						{history.isLoading && <LoadingSkeleton variant="card" rows={2} />}
						{history.isError && <ErrorState onRetry={() => void history.refetch()} />}
						{history.data?.length === 0 && (
							<p className="py-5 text-sm text-(--color-foreground-tertiary)">该 spec 尚无已保存运行。</p>
						)}
						<div className="grid gap-2 md:grid-cols-2">
							{history.data?.map((item) => (
								<div
									key={item.run_id}
									className={
										item.run_id === selectedRunId
											? "rounded-(--radius-md) border border-(--color-accent) bg-(--color-accent)/5 p-3"
											: "rounded-(--radius-md) border border-(--color-border-subtle) bg-(--color-surface-1) p-3"
									}
								>
									<div className="flex items-start gap-2">
										<input
											type="checkbox"
											aria-label={`加入运行对比 ${shortRunId(item.run_id)}`}
											checked={compareIds.includes(item.run_id)}
											onChange={() => toggleCompare(item.run_id)}
										/>
										<button type="button" className="min-w-0 flex-1 text-left" onClick={() => commitRunId(item.run_id)}>
											<span className="block font-mono text-xs font-medium">{shortRunId(item.run_id)}</span>
											<span className="mt-1 block text-[11px] text-(--color-foreground-tertiary)">
												{new Date(item.as_of).toLocaleString("zh-CN")} · {item.candidates.length} in /{" "}
												{item.exclusions.length} out
											</span>
										</button>
										<span className="rounded-full border border-(--color-border-subtle) px-2 py-0.5 text-xs uppercase">
											{item.status}
										</span>
									</div>
								</div>
							))}
						</div>
					</section>

					<section
						data-info-level="l1"
						data-info-unit="selection-results"
						aria-labelledby="selection-results-heading"
						className="p-(--density-panel-padding)"
					>
						<div className="mb-3 flex items-center justify-between">
							<h2 id="selection-results-heading" className="text-sm font-semibold">
								候选与排除
							</h2>
							<div role="tablist" aria-label="Selection 结果">
								<Button
									type="button"
									size="sm"
									variant={tab === "candidates" ? "secondary" : "ghost"}
									role="tab"
									aria-selected={tab === "candidates"}
									onClick={() => selectTab("candidates")}
								>
									入选 {run?.candidates.length ?? 0}
								</Button>
								<Button
									type="button"
									size="sm"
									variant={tab === "exclusions" ? "secondary" : "ghost"}
									role="tab"
									aria-selected={tab === "exclusions"}
									onClick={() => selectTab("exclusions")}
								>
									排除 {run?.exclusions.length ?? 0}
								</Button>
							</div>
						</div>
						{exactRun.isLoading && <LoadingSkeleton variant="table" rows={5} />}
						{exactRun.isError && <ErrorState onRetry={() => void exactRun.refetch()} />}
						{!run && !exactRun.isLoading && !exactRun.isError && (
							<p className="py-8 text-center text-sm text-(--color-foreground-tertiary)">
								该 spec
								尚无已选中的运行。在上方配置筛选条件与因子权重并点击「创建运行」；创建后会在此展示候选、排除与贡献证据。
							</p>
						)}
						{run && currentItems?.length === 0 && (
							<p className="py-8 text-center text-sm text-(--color-foreground-tertiary)">
								此运行没有{tab === "candidates" ? "入选候选" : "排除记录"}。
							</p>
						)}
						{run && tab === "candidates" && run.candidates.length > 0 && (
							<div className="overflow-x-auto rounded-(--radius-md) border border-(--color-border-subtle)">
								<table className="w-full text-left text-xs">
									<thead className="bg-(--color-surface-strip) text-(--color-foreground-tertiary)">
										<tr>
											<th className="px-3 py-2">Rank</th>
											<th className="px-3 py-2">标的</th>
											<th className="px-3 py-2">Score</th>
											<th className="px-3 py-2">Factor contribution</th>
										</tr>
									</thead>
									<tbody className="divide-y divide-(--color-border-subtle)">
										{run.candidates.map((candidate) => (
											<tr key={candidate.instrument_id} data-info-level="l3" data-info-unit="selection-candidate">
												<td className="px-3 py-3 font-mono text-base">#{candidate.rank}</td>
												<td className="px-3 py-3">
													<a
														className="font-medium hover:text-(--color-accent)"
														href={`/instruments/${encodeURIComponent(candidate.instrument_id)}?tab=chart&selectionRunId=${encodeURIComponent(run.run_id)}${runObserveDate ? `&observeDate=${runObserveDate}` : ""}`}
													>
														{candidate.instrument_name}
													</a>
													<span className="mt-1 block font-mono text-[11px] text-(--color-foreground-tertiary)">
														{candidate.instrument_id}{" "}
														<a
															aria-label={`技术证据 ${candidate.instrument_id}`}
															className="underline decoration-dotted underline-offset-2 hover:text-(--color-accent)"
															href={`/instruments/${encodeURIComponent(candidate.instrument_id)}?tab=technical&selectionRunId=${encodeURIComponent(run.run_id)}`}
														>
															技术证据
														</a>
													</span>
												</td>
												<td className="px-3 py-3 font-mono text-sm">{candidate.score.toFixed(4)}</td>
												<td className="px-3 py-3">
													<div className="flex flex-wrap gap-2">
														{candidate.factor_contributions.map((factor) => (
															<span
																key={factor.factor_name}
																className="rounded-full border border-(--color-border-subtle) px-2 py-1"
															>
																<span className="text-(--color-foreground-tertiary)">{factor.factor_name}</span>{" "}
																<span className="ml-1 font-mono">{factor.contribution.toFixed(4)}</span>
															</span>
														))}
													</div>
												</td>
											</tr>
										))}
									</tbody>
								</table>
							</div>
						)}
						{run && tab === "exclusions" && run.exclusions.length > 0 && (
							<div className="grid gap-2">
								{run.exclusions.map((item) => (
									<article
										key={item.instrument_id}
										className="grid grid-cols-[minmax(0,1fr)_auto] gap-3 rounded-(--radius-md) border border-(--color-border-subtle) bg-(--color-surface-1) p-3 text-xs"
									>
										<div>
											<h3 className="font-medium">
												<a
													className="hover:text-(--color-accent)"
													href={`/instruments/${encodeURIComponent(item.instrument_id)}?tab=chart&selectionRunId=${encodeURIComponent(run.run_id)}${runObserveDate ? `&observeDate=${runObserveDate}` : ""}`}
												>
													{item.instrument_name}
												</a>{" "}
												<span className="font-mono text-(--color-foreground-tertiary)">{item.instrument_id}</span>
											</h3>
											<p className="mt-1 text-(--color-foreground-tertiary)">{item.detail}</p>
										</div>
										<div className="text-right">
											<p className="font-mono text-(--color-risk-warning-fg)">{item.reason_code}</p>
											<p className="mt-1 text-xs uppercase text-(--color-foreground-tertiary)">{item.stage}</p>
										</div>
									</article>
								))}
							</div>
						)}
					</section>
				</div>
			}
			detail={<SelectionRunDetail diff={comparison.data ?? null} run={run} />}
		/>
	);
}
