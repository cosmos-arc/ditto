import type { ReactElement } from "react";
import { ContextSection } from "@/components/domain/context-section";
import type { ConstraintSpec, StrategySpec } from "@/types/strategy";

interface ConstraintsPipelineProps {
	readonly constraints: readonly ConstraintSpec[];
	/** 工作副本更新器（与 `useStrategyStudioStore.updateSpec` 同构）。 */
	readonly onChange: (updater: (draft: StrategySpec) => StrategySpec) => void;
	readonly onSelect: (key: string | null) => void;
	readonly selectedKey: string | null;
}

const NEW_CONSTRAINT: ConstraintSpec = { type: "new_constraint", params: {} };

function constraintKey(index: number): string {
	return `constraint-${index}`;
}

/**
 * 约束流水线：`constraints` 数组的 add/remove/reorder/select。
 *
 * legacy spec 固定结构中 `constraints` 是唯一可完整 CRUD 的数组（scorer/selector/execution
 * 为单例槽位）。所有变异通过 `onChange(updater)` 上抛不可变更新；选中交给 NodeInspector
 * 编辑该约束的 `params`。
 */
export function ConstraintsPipeline({
	constraints,
	onChange,
	onSelect,
	selectedKey,
}: ConstraintsPipelineProps): ReactElement {
	function move(from: number, to: number): void {
		onChange((draft) => {
			const next = [...draft.constraints];
			[next[from], next[to]] = [next[to], next[from]];
			return { ...draft, constraints: next };
		});
	}

	function remove(index: number): void {
		onChange((draft) => ({ ...draft, constraints: draft.constraints.filter((_, i) => i !== index) }));
	}

	return (
		<ContextSection title="约束流水线" count={constraints.length}>
			<div className="flex flex-col gap-(--section-gap) p-(--density-panel-padding)">
				{constraints.length === 0 ? (
					<p className="text-xs text-(--color-foreground-tertiary)">暂无约束</p>
				) : (
					<ul className="flex flex-col gap-1">
						{constraints.map((constraint, index) => {
							const key = constraintKey(index);
							const isSelected = selectedKey === key;
							return (
								<li
									key={key}
									data-selected={isSelected}
									className="flex items-center gap-2 rounded-sm p-(--density-panel-padding) transition-colors hover:bg-(--color-interaction-hover-subtle-bg)"
								>
									<button type="button" className="flex-1 text-left text-sm" onClick={() => onSelect(key)}>
										{constraint.type || `约束 ${index + 1}`}
									</button>
									<button
										type="button"
										aria-label={`上移约束 ${index + 1}`}
										disabled={index === 0}
										onClick={() => move(index, index - 1)}
										className="rounded-sm px-2 py-0.5 text-xs text-(--color-foreground-secondary) hover:bg-(--color-interaction-hover-subtle-bg) disabled:opacity-40"
									>
										上移
									</button>
									<button
										type="button"
										aria-label={`下移约束 ${index + 1}`}
										disabled={index === constraints.length - 1}
										onClick={() => move(index, index + 1)}
										className="rounded-sm px-2 py-0.5 text-xs text-(--color-foreground-secondary) hover:bg-(--color-interaction-hover-subtle-bg) disabled:opacity-40"
									>
										下移
									</button>
									<button
										type="button"
										aria-label={`删除约束 ${index + 1}`}
										onClick={() => remove(index)}
										className="rounded-sm px-2 py-0.5 text-xs text-(--color-led-danger) hover:bg-(--color-interaction-hover-subtle-bg)"
									>
										删除
									</button>
								</li>
							);
						})}
					</ul>
				)}
				<button
					type="button"
					onClick={() => onChange((draft) => ({ ...draft, constraints: [...draft.constraints, NEW_CONSTRAINT] }))}
					className="self-start rounded-sm bg-(--brand-accent) px-3 py-1 text-sm text-white transition-colors hover:bg-(--brand-accent-hover)"
				>
					添加约束
				</button>
			</div>
		</ContextSection>
	);
}
