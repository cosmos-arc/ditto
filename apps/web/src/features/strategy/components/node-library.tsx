import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { ContextSection } from "@/components/domain/context-section";
import { DittoErrorBoundary } from "@/lib/error-boundary";
import type { NodeDescriptorView } from "@/types/strategy";
import { useNodeDescriptors } from "../hooks";

interface NodeLibraryProps {
	readonly onAdd?: (descriptor: NodeDescriptorView) => void;
	readonly onPreviewFactors?: () => void;
}

/**
 * 节点库（Studio 左栏只读调色板）。
 *
 * 数据源 `GET /api/v1/research/node-descriptors` → `NodeDescriptorView`。按 `category`
 * （UNIVERSE/FACTOR_SET/SCORER/SELECTOR/ALLOCATOR/EXECUTION_ASSUMPTION/VALIDATION）
 * 分组展示受治理的流水线节点类型，供流水线编辑器 add/configure 参考。
 */
export function NodeLibrary({ onAdd, onPreviewFactors }: NodeLibraryProps) {
	const { data, isLoading, isError } = useNodeDescriptors();
	const descriptors = data ?? [];
	const categories = [...new Set(descriptors.map((d) => d.category))];

	return (
		<DittoErrorBoundary>
			<div className="flex flex-col gap-2 p-2">
				<div className="flex items-center justify-between px-1">
					<span className="text-xs font-medium uppercase tracking-[0.12em] text-(--color-foreground-tertiary)">
						策略资源
					</span>
					<button
						type="button"
						onClick={onPreviewFactors}
						className="rounded-(--radius-sm) border border-(--color-border-subtle) px-2 py-1 text-xs text-(--color-foreground-secondary) hover:bg-(--color-interaction-hover-subtle-bg)"
					>
						因子预览
					</button>
				</div>
				<ContextSection title="节点库">
					{isLoading ? (
						<LoadingSkeleton />
					) : isError || descriptors.length === 0 ? (
						<p className="text-sm text-(--color-foreground-tertiary)">暂无可用节点</p>
					) : (
						<ul className="flex flex-col gap-2">
							{categories.map((category) => (
								<li key={category}>
									<p className="px-1 text-[9px] font-medium tracking-[0.08em] text-(--color-foreground-tertiary)">
										{category}
									</p>
									<ul className="flex flex-col gap-1">
										{descriptors
											.filter((d) => d.category === category)
											.map((d) => (
												<li
													key={d.nodeType}
													className="flex items-center justify-between rounded-sm px-2 py-1.5 text-xs transition-colors hover:bg-(--color-interaction-hover-subtle-bg)"
												>
													<div className="min-w-0">
														<span className="block truncate">{d.displayName}</span>
														<span className="block truncate font-data text-xs text-(--color-foreground-tertiary)">
															{d.nodeType}@{d.version}
														</span>
													</div>
													{d.category === "FILTER" ? (
														<button
															type="button"
															onClick={() => onAdd?.(d)}
															className="rounded-(--radius-sm) border border-(--color-border-subtle) px-2 py-1 text-xs"
														>
															添加
														</button>
													) : (
														<span className="text-xs text-(--color-foreground-tertiary)">固定槽位</span>
													)}
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
