import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { ContextSection } from "@/components/domain/context-section";
import { DittoErrorBoundary } from "@/lib/error-boundary";
import { useNodeDescriptors } from "../hooks";

/**
 * 节点库（Studio 左栏只读调色板）。
 *
 * 数据源 `GET /v1/research/node-descriptors` → `NodeDescriptorView`。按 `category`
 * （UNIVERSE/FACTOR_SET/SCORER/SELECTOR/ALLOCATOR/EXECUTION_ASSUMPTION/VALIDATION）
 * 分组展示受治理的流水线节点类型，供流水线编辑器 add/configure 参考。
 */
export function NodeLibrary() {
	const { data, isLoading, isError } = useNodeDescriptors();
	const descriptors = data ?? [];
	const categories = [...new Set(descriptors.map((d) => d.category))];

	return (
		<DittoErrorBoundary>
			<div className="flex flex-col gap-[var(--section-gap)] p-[var(--density-panel-padding)]">
				<ContextSection title="节点库">
					{isLoading ? (
						<LoadingSkeleton />
					) : isError || descriptors.length === 0 ? (
						<p className="text-sm text-(--color-foreground-tertiary)">暂无可用节点</p>
					) : (
						<ul className="flex flex-col gap-[var(--section-gap)]">
							{categories.map((category) => (
								<li key={category}>
									<p className="text-xs font-medium text-(--color-foreground-tertiary)">{category}</p>
									<ul className="flex flex-col gap-1">
										{descriptors
											.filter((d) => d.category === category)
											.map((d) => (
												<li
													key={d.nodeType}
													className="flex items-center justify-between rounded-sm px-2 py-1 text-sm transition-colors hover:bg-(--color-interaction-hover-subtle-bg)"
												>
													<span>{d.displayName}</span>
													<span className="font-data text-xs text-(--color-foreground-tertiary)">{d.nodeType}</span>
												</li>
											))}
									</ul>
								</li>
							))}
						</ul>
					)}
				</ContextSection>
			</div>
		</DittoErrorBoundary>
	);
}
