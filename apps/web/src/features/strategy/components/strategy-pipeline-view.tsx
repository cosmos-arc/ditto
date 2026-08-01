import type { KeyboardEvent, ReactElement } from "react";
import { ContextSection } from "@/components/domain/context-section";
import type { NodeDescriptorView, StrategySpec } from "@/types/strategy";
import {
	buildStrategyPipeline,
	movePipelineNode,
	removePipelineNode,
	type StrategyPipelineNode,
} from "../api/pipeline-model";

interface StrategyPipelineViewProps {
	readonly spec: StrategySpec;
	readonly descriptors: readonly NodeDescriptorView[];
	readonly onChange: (updater: (draft: StrategySpec) => StrategySpec) => void;
	readonly onSelect: (key: string | null) => void;
	readonly selectedKey: string | null;
}

/** 固定语法 Universe → FactorSet → Filter* → ... → Validation 的有序编辑器。 */
export function StrategyPipelineView({
	spec,
	descriptors,
	onChange,
	onSelect,
	selectedKey,
}: StrategyPipelineViewProps): ReactElement {
	const nodes = buildStrategyPipeline(spec, descriptors);
	const editableFilters = nodes.filter((node) => !node.fixed && !node.readOnly);

	function move(node: StrategyPipelineNode, direction: -1 | 1): void {
		onChange((draft) => movePipelineNode(draft, node, direction, descriptors));
	}

	function handleNodeKeyDown(event: KeyboardEvent<HTMLButtonElement>, node: StrategyPipelineNode): void {
		if (!event.altKey || node.fixed || node.readOnly) return;
		if (event.key === "ArrowUp") {
			event.preventDefault();
			move(node, -1);
		}
		if (event.key === "ArrowDown") {
			event.preventDefault();
			move(node, 1);
		}
	}

	return (
		<ContextSection title="受约束流水线" count={nodes.length}>
			<ol className="flex flex-col gap-1 p-(--density-panel-padding)" data-slot="strategy-pipeline">
				{nodes.map((node) => {
					const editableIndex = editableFilters.findIndex((item) => item.key === node.key);
					return (
						<li
							key={node.key}
							data-selected={selectedKey === node.key}
							data-fixed={node.fixed}
							data-read-only={node.readOnly}
							data-allowed-predecessor={node.allowedPredecessor ?? undefined}
							data-allowed-successor={node.allowedSuccessor ?? undefined}
							className="grid grid-cols-[2rem_minmax(0,1fr)_auto] items-center gap-2 rounded-(--radius-sm) border border-(--color-border-subtle) px-2 py-2 data-[selected=true]:border-(--color-border-strong) data-[selected=true]:bg-(--color-interaction-selected-bg)"
						>
							<span className="font-data text-xs text-(--color-foreground-tertiary)">{node.category}</span>
							<button
								type="button"
								onClick={() => onSelect(node.key)}
								onKeyDown={(event) => handleNodeKeyDown(event, node)}
								className="min-w-0 text-left"
							>
								<span className="block truncate text-sm font-medium">{node.displayName}</span>
								<span className="block truncate font-data text-xs text-(--color-foreground-tertiary)">
									{node.identity}
								</span>
								{node.readOnly && <span className="text-xs text-(--color-led-warning)">未知 descriptor，只读</span>}
							</button>
							<div className="flex items-center gap-1">
								{!node.fixed && !node.readOnly && (
									<>
										<button
											type="button"
											aria-label={`上移 ${node.displayName}`}
											disabled={editableIndex <= 0}
											onClick={() => move(node, -1)}
											className="rounded-(--radius-sm) px-2 py-1 text-xs disabled:opacity-40"
										>
											↑
										</button>
										<button
											type="button"
											aria-label={`下移 ${node.displayName}`}
											disabled={editableIndex < 0 || editableIndex === editableFilters.length - 1}
											onClick={() => move(node, 1)}
											className="rounded-(--radius-sm) px-2 py-1 text-xs disabled:opacity-40"
										>
											↓
										</button>
										<button
											type="button"
											aria-label={`删除 ${node.displayName}`}
											onClick={() => onChange((draft) => removePipelineNode(draft, node))}
											className="rounded-(--radius-sm) px-2 py-1 text-xs text-(--color-led-danger)"
										>
											删除
										</button>
									</>
								)}
							</div>
						</li>
					);
				})}
			</ol>
		</ContextSection>
	);
}

export { StrategyPipelineView as ConstraintsPipeline };
