import { StudioLayout } from "@/features/shell";
import { StrategyHeader } from "./strategy-header";
import { FactorBrowser } from "./factor-browser";

export function StrategyPage() {
	return (
		<StudioLayout
			main={
				<div className="flex flex-col gap-[var(--section-gap)] p-[var(--density-panel-padding)]">
					<StrategyHeader id="strat-001" />
					<div className="flex h-full items-center justify-center text-sm text-(--color-foreground-tertiary)">
						策略编辑器 — 待实现
					</div>
				</div>
			}
		/>
	);
}
