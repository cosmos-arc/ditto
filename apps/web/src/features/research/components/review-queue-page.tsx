/**
 * Review queue 列表页（`/research/reviews`）。
 *
 * 列出 REVIEW 态版本（待审查 + 已批准待发布）；每项链接到 review-detail
 * （experimentId + strategyId/version search）。`experimentId` 为 null（尚无
 * review packet）的项渲染为禁用行——绝不伪造可审查状态。
 */

import { Link } from "@tanstack/react-router";
import type { ReactElement } from "react";
import { CatalogLayout, Panel, PanelBody, PanelHeader } from "@/features/shell";
import type { ReviewQueueEntry } from "@/types/review";
import { useReviews } from "../hooks";

function QueueRow({ entry }: { readonly entry: ReviewQueueEntry }): ReactElement {
	const cells = (
		<>
			<span className="font-data text-(--color-foreground-tertiary)">
				{entry.strategyId} · v{entry.version}
			</span>
			<span className="text-(--color-foreground-secondary)">{entry.state}</span>
			<span className="text-(--color-foreground-secondary)">{entry.reviewOutcome}</span>
			<span className="font-data text-(--color-foreground-tertiary)">{entry.createdAt.slice(0, 10)}</span>
		</>
	);
	if (entry.experimentId === null) {
		return (
			<div
				className="grid grid-cols-[1fr_5rem_5rem_6rem] items-center px-3 py-2 text-sm opacity-50"
				title="尚无持久化 review packet"
			>
				{cells}
			</div>
		);
	}
	return (
		<Link
			to="/research/reviews/$id"
			params={{ id: entry.experimentId }}
			search={{ strategyId: entry.strategyId, version: entry.version }}
			className="grid grid-cols-[1fr_5rem_5rem_6rem] items-center px-3 py-2 text-sm transition-colors hover:bg-(--color-interaction-hover-subtle-bg)"
		>
			{cells}
		</Link>
	);
}

export function ReviewQueuePage(): ReactElement {
	const { data, isLoading } = useReviews();
	const entries = data ?? [];

	return (
		<CatalogLayout
			toolbar={
				<div className="flex h-full items-center justify-between border-b border-(--color-border-subtle) bg-(--color-surface-strip) px-4">
					<div>
						<p className="text-sm font-medium text-(--color-foreground)">审查队列</p>
						<p className="text-xs text-(--color-foreground-tertiary)">待审查与待发布的策略版本</p>
					</div>
					<span className="font-data text-xs text-(--color-foreground-tertiary)">{entries.length} 项</span>
				</div>
			}
			main={
				<Panel className="m-4">
					<PanelHeader title="Reviews" count={entries.length} />
					<PanelBody>
						<div className="divide-y divide-(--color-border-subtle)">
							{isLoading && entries.length === 0 ? (
								<p className="px-3 py-2 text-sm text-(--color-foreground-tertiary)">加载中…</p>
							) : entries.length === 0 ? (
								<p className="px-3 py-2 text-sm text-(--color-foreground-tertiary)">暂无待审查版本。</p>
							) : (
								entries.map((entry) => <QueueRow key={`${entry.strategyId}-${entry.version}`} entry={entry} />)
							)}
						</div>
					</PanelBody>
				</Panel>
			}
			detail={
				<Panel className="m-4 ml-0">
					<PanelHeader title="Review Detail" />
					<PanelBody className="p-(--density-panel-padding) text-sm text-(--color-foreground-secondary)">
						选择左侧版本后，展示 11 hard-gate、证据 hash、spec diff 与血统，并执行批准/发布。
					</PanelBody>
				</Panel>
			}
		/>
	);
}
