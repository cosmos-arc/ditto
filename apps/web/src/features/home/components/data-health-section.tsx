import { useDataHealth } from "../hooks";
import { ContextSection } from "@/components/domain/context-section";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";

const STATUS_DOT_COLOR: Record<string, string> = {
	healthy: "bg-(--color-system-healthy-fg)",
	warning: "bg-(--color-system-degraded-fg)",
	error: "bg-(--color-system-down-fg)",
};

const STATUS_TEXT_COLOR: Record<string, string> = {
	healthy: "text-(--color-system-healthy-fg)",
	warning: "text-(--color-system-degraded-fg)",
	error: "text-(--color-system-down-fg)",
};

/**
 * DataHealthSection — sidebar "数据健康" section.
 * Matches prototype .context-section with health-gauge + health-items.
 */
export function DataHealthSection() {
	const { data, isLoading } = useDataHealth();

	return (
		<ContextSection title="数据健康" defaultOpen>
			{isLoading && <LoadingSkeleton variant="table" rows={4} />}
			{data && (
				<div className="flex flex-col gap-1">
					{/* Health summary gauge bar */}
					<div className="mb-1.5 flex gap-0.5 h-[3px] rounded-sm overflow-hidden">
						{data.providers.map((provider) => (
							<div
								key={provider.label}
								className={`flex-1 rounded-sm ${provider.status === "healthy" ? "bg-(--color-system-healthy-fg)" : "bg-(--color-system-degraded-fg)"}`}
								title={provider.label}
							/>
						))}
					</div>

					{/* Health items */}
					{data.providers.map((provider) => (
						<div
							key={provider.label}
							className="flex items-center justify-between rounded-[var(--radius-sm)] px-2 py-1.5 transition-colors hover:bg-(--color-interaction-hover-subtle-bg)"
						>
							<div className="flex items-center gap-1.5">
								<span
									className={`inline-block size-1.5 rounded-full ${STATUS_DOT_COLOR[provider.status] ?? "bg-(--color-foreground-disabled)"}`}
								/>
								<span className="text-xs text-(--color-foreground-secondary)">
									{provider.label}
								</span>
							</div>
							<span
								className={`text-xs ${STATUS_TEXT_COLOR[provider.status] ?? "text-(--color-foreground-tertiary)"}`}
							>
								{provider.status === "healthy" ? "正常" : provider.statusText.split("·")[0].trim()}
							</span>
						</div>
					))}
				</div>
			)}
			{data && (
				<div className="px-3 pb-2">
					<button
						type="button"
						className="text-xs text-(--color-foreground-secondary) transition-colors hover:bg-(--color-interaction-hover-subtle-bg) rounded-[var(--radius-sm)] px-1.5 py-0.5"
					>
						查看详情 →
					</button>
				</div>
			)}
		</ContextSection>
	);
}
