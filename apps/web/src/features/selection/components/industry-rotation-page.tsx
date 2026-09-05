import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { Button } from "@/components/ui/button";
import { CatalogLayout, Panel, PanelBody, PanelHeader } from "@/features/shell";
import { ErrorState } from "@/lib/error-boundary";
import { StaleIndicator } from "@/lib/stale-indicator";
import { ContextActions } from "@/providers";
import { getIndustryRotation, selectionKeys } from "../api";

function querySnapshotId(): string {
	return new URLSearchParams(window.location.search).get("snapshotId") ?? "";
}

export function IndustryRotationPage({ initialSnapshotId }: { readonly initialSnapshotId?: string }) {
	const firstSnapshotId = initialSnapshotId ?? querySnapshotId();
	const [input, setInput] = useState(firstSnapshotId);
	const [snapshotId, setSnapshotId] = useState(firstSnapshotId);
	const [selectedIndustryId, setSelectedIndustryId] = useState<string | null>(null);
	const query = useQuery({
		queryKey: selectionKeys.rotation(snapshotId || "none"),
		queryFn: () => getIndustryRotation(snapshotId),
		enabled: snapshotId.length > 0,
		staleTime: Number.POSITIVE_INFINITY,
	});
	useEffect(() => {
		const first = query.data?.rankings[0];
		if (first && !query.data?.rankings.some((item) => item.industry_id === selectedIndustryId)) {
			setSelectedIndustryId(first.industry_id);
		}
	}, [query.data, selectedIndustryId]);
	const selected = query.data?.rankings.find((item) => item.industry_id === selectedIndustryId) ?? null;

	return (
		<CatalogLayout
			toolbar={
				<div
					data-info-level="l1"
					data-info-unit="rotation-toolbar"
					className="flex items-end gap-3 border-b border-(--color-border-subtle) bg-(--color-surface-strip) px-4 py-2"
				>
					<div className="mr-auto">
						<p className="text-[11px] font-semibold tracking-[0.16em] text-(--color-accent)">INDUSTRY ROTATION</p>
						<p className="text-xs text-(--color-foreground-tertiary)">按 snapshot identity 读取，不回退 latest</p>
					</div>
					<label className="grid min-w-96 gap-1 text-xs text-(--color-foreground-tertiary)">
						Snapshot ID
						<input
							aria-label="行业轮动 Snapshot ID"
							className="rounded-(--radius-sm) border border-(--color-border-primary) bg-(--color-surface-1) px-2 py-1.5 font-mono text-xs text-(--color-foreground)"
							value={input}
							onChange={(event) => setInput(event.currentTarget.value)}
						/>
					</label>
					<Button type="button" onClick={() => setSnapshotId(input.trim())} disabled={!input.trim()}>
						读取快照
					</Button>
				</div>
			}
			main={
				<div
					data-info-level="l1"
					data-info-unit="rotation-main"
					className="h-full overflow-y-auto p-(--density-panel-padding)"
				>
					<StaleIndicator isStale={Boolean(query.data && query.isFetching)} />
					{!snapshotId && (
						<div className="grid min-h-64 place-items-center rounded-(--radius-lg) border border-dashed border-(--color-border-primary) text-sm text-(--color-foreground-tertiary)">
							输入 SelectionRun 引用的行业轮动 snapshot ID。
						</div>
					)}
					{query.isLoading && <LoadingSkeleton variant="table" rows={8} />}
					{query.isError && <ErrorState onRetry={() => void query.refetch()} />}
					{query.data && query.data.rankings.length === 0 && (
						<p className="py-12 text-center text-sm text-(--color-foreground-tertiary)">该快照没有可见行业排名。</p>
					)}
					{query.data && query.data.rankings.length > 0 && (
						<section
							aria-labelledby="rotation-ranks"
							className="overflow-hidden rounded-(--radius-lg) border border-(--color-border-subtle) bg-(--color-surface-1)"
						>
							<header className="flex items-center justify-between border-b border-(--color-border-subtle) bg-(--color-surface-strip) px-4 py-3">
								<div>
									<h1 id="rotation-ranks" className="text-sm font-semibold">
										行业排名
									</h1>
									<p className="mt-1 text-xs text-(--color-foreground-tertiary)">
										{new Date(query.data.as_of).toLocaleString("zh-CN")} · {query.data.algorithm_version}
									</p>
								</div>
								<span className="rounded-full border border-(--color-border-subtle) px-2 py-1 text-xs uppercase">
									{query.data.status}
								</span>
							</header>
							<div className="divide-y divide-(--color-border-subtle)">
								{query.data.rankings.map((rank) => (
									<button
										key={rank.industry_id}
										type="button"
										aria-label={`检查 ${rank.industry_name}`}
										onClick={() => setSelectedIndustryId(rank.industry_id)}
										className={
											rank.industry_id === selectedIndustryId
												? "grid w-full grid-cols-[4rem_minmax(0,1fr)_7rem] items-center gap-3 bg-(--color-accent)/5 px-4 py-3 text-left"
												: "grid w-full grid-cols-[4rem_minmax(0,1fr)_7rem] items-center gap-3 px-4 py-3 text-left hover:bg-(--color-interaction-hover-subtle-bg)"
										}
									>
										<span className="font-mono text-xl text-(--color-accent)">#{rank.rank}</span>
										<span>
											<strong className="text-sm font-medium">{rank.industry_name}</strong>
											<small className="ml-2 font-mono text-(--color-foreground-tertiary)">{rank.industry_id}</small>
										</span>
										<span className="text-right font-mono text-sm">{rank.score.toFixed(4)}</span>
									</button>
								))}
							</div>
						</section>
					)}
				</div>
			}
			detail={
				<Panel data-info-level="l2" data-info-unit="rotation-inspector" className="m-4 ml-0 h-[calc(100%-2rem)]">
					<PanelHeader title="行业 Inspector" subtitle={query.data?.membership_version ?? "snapshot required"} />
					<PanelBody className="space-y-5 overflow-y-auto p-4">
						{selected && query.data ? (
							<>
								<section>
									<h2 className="text-lg font-semibold">{selected.industry_name}</h2>
									<p className="mt-1 font-mono text-xs text-(--color-foreground-tertiary)">
										{selected.industry_id} · rank {selected.rank} · {selected.score.toFixed(4)}
									</p>
								</section>
								<section className="border-t border-(--color-border-subtle) pt-4">
									<h3 className="text-xs font-semibold tracking-wide text-(--color-foreground-secondary)">
										SCORE CONTRIBUTIONS
									</h3>
									<div className="mt-2 space-y-2">
										{selected.contributions.map((item) => (
											<div
												key={item.metric}
												className="rounded-(--radius-sm) border border-(--color-border-subtle) bg-(--color-surface-1) p-2 text-xs"
											>
												<div className="flex justify-between">
													<span>{item.metric}</span>
													<span className="font-mono">{item.contribution.toFixed(4)}</span>
												</div>
												<p className="mt-1 font-mono text-xs text-(--color-foreground-tertiary)">
													{item.value?.toFixed(4) ?? "missing"} × {item.weight.toFixed(2)}
												</p>
											</div>
										))}
									</div>
								</section>
								{selected.missing_inputs.length > 0 && (
									<section className="border-t border-(--color-border-subtle) pt-4">
										<h3 className="text-xs font-semibold text-(--color-risk-warning-fg)">MISSING INPUTS</h3>
										<ul className="mt-2 text-xs text-(--color-foreground-tertiary)">
											{selected.missing_inputs.map((item) => (
												<li key={item}>{item}</li>
											))}
										</ul>
									</section>
								)}
								<section className="border-t border-(--color-border-subtle) pt-4">
									<h3 className="text-xs font-semibold tracking-wide text-(--color-foreground-secondary)">
										SNAPSHOT CONTEXT
									</h3>
									<p className="mt-2 text-xs">{query.data.membership_version}</p>
									<p className="mt-1 break-all font-mono text-xs text-(--color-foreground-tertiary)">
										{query.data.snapshot_id}
									</p>
								</section>
								<section className="border-t border-(--color-border-subtle) pt-4">
									<ContextActions
										contextId={query.data.snapshot_id}
										contextType="selection"
										evidenceObjective="解释精确行业排名"
									/>
								</section>
							</>
						) : (
							<p className="text-sm text-(--color-foreground-tertiary)">选择一个行业检查贡献和缺失输入。</p>
						)}
					</PanelBody>
				</Panel>
			}
		/>
	);
}
