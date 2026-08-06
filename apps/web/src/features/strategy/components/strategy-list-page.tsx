import { Link } from "@tanstack/react-router";
import { CatalogLayout, Panel, PanelBody, PanelHeader } from "@/features/shell";
import { useStrategies } from "../hooks";

export function StrategyListPage() {
	const { data, isLoading } = useStrategies();
	const strategies = data ?? [];

	return (
		<CatalogLayout
			toolbar={
				<div className="flex h-full items-center justify-between border-b border-(--color-border-subtle) bg-(--color-surface-strip) px-4">
					<div>
						<p className="text-sm font-medium text-(--color-foreground)">策略列表</p>
						<p className="text-xs text-(--color-foreground-tertiary)">研究策略、版本和上线状态</p>
					</div>
				</div>
			}
			main={
				<Panel className="m-4">
					<PanelHeader title="Strategies" count={strategies.length} />
					<PanelBody>
						<div className="divide-y divide-(--color-border-subtle)">
							{isLoading && strategies.length === 0 ? (
								<p className="px-3 py-2 text-sm text-(--color-foreground-tertiary)">加载中…</p>
							) : (
								strategies.map((s) => (
									<Link
										key={s.strategyId}
										to="/research/strategies/$id"
										params={{ id: s.strategyId }}
										className="grid grid-cols-[7rem_1fr_6rem] items-center px-3 py-2 text-sm transition-colors hover:bg-(--color-interaction-hover-subtle-bg)"
									>
										<span className="font-data text-(--color-foreground-tertiary)">{s.strategyId}</span>
										<span className="text-(--color-foreground)">{s.name}</span>
										<span className="font-data text-(--color-foreground-secondary)">{s.lifecycleState}</span>
									</Link>
								))
							)}
						</div>
					</PanelBody>
				</Panel>
			}
			detail={
				<Panel className="m-4 ml-0">
					<PanelHeader title="Promotion" />
					<PanelBody className="p-(--density-panel-padding) text-sm text-(--color-foreground-secondary)">
						选择策略后显示发布门禁、最近回测和依赖因子。
					</PanelBody>
				</Panel>
			}
		/>
	);
}
