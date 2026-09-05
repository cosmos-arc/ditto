import { Panel, PanelBody, PanelHeader } from "@/features/shell";
import type { DataProductCheck, DataProductQuality as DataProductQualityModel } from "../api";

interface DataProductQualityProps {
	readonly data?: DataProductQualityModel | undefined;
	readonly isLoading: boolean;
	readonly isError: boolean;
}

function CheckGroup({ title, checks }: { readonly title: string; readonly checks: readonly DataProductCheck[] }) {
	return (
		<section aria-label={title}>
			<h3 className="text-xs font-medium text-(--color-foreground-secondary)">{title}</h3>
			<ul className="mt-2 divide-y divide-(--color-border-subtle) rounded-(--radius-sm) border border-(--color-border-subtle)">
				{checks.length === 0 && <li className="p-3 text-xs text-(--color-foreground-tertiary)">无可用检查证据</li>}
				{checks.map((check) => (
					<li
						key={`${check.name}-${check.evidence_uri}`}
						className="grid gap-1 p-3 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center"
					>
						<div className="min-w-0">
							<p className="text-sm text-(--color-foreground)">{check.name}</p>
							<code className="block truncate font-code text-xs text-(--color-foreground-tertiary)">
								{check.evidence_uri}
							</code>
						</div>
						<span
							className={
								check.passed
									? "text-xs font-medium text-(--color-system-healthy-fg)"
									: "text-xs font-medium text-(--color-system-down-fg)"
							}
						>
							{check.passed ? "✓ 通过" : "! 失败"}
						</span>
					</li>
				))}
			</ul>
		</section>
	);
}

export function DataProductQuality({ data, isLoading, isError }: DataProductQualityProps) {
	return (
		<Panel className="h-full" data-info-level="l1" data-info-unit="data-product-quality">
			<PanelHeader title="质量与 PIT" subtitle={data?.dq_rule_version} />
			<PanelBody className="p-(--density-panel-padding)">
				{isLoading && (
					<div
						role="status"
						aria-label="正在加载质量证据"
						className="h-24 animate-pulse rounded-(--radius-sm) bg-(--color-surface-muted)"
					/>
				)}
				{isError && (
					<p role="alert" className="text-sm text-(--color-risk-critical-fg)">
						质量证据暂不可用，消费保持阻塞。
					</p>
				)}
				{data && (
					<div className="grid gap-5 xl:grid-cols-2">
						<CheckGroup title="DQ 与 Provider 差异" checks={data.dq_results} />
						<CheckGroup title="PIT Replay" checks={data.pit_replay_results} />
						<CheckGroup title="新鲜度与恢复" checks={[...data.freshness_results, ...data.recovery_results]} />
						<CheckGroup title="消费者契约" checks={data.consumer_results} />
					</div>
				)}
			</PanelBody>
		</Panel>
	);
}
