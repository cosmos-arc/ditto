import type { ReactElement } from "react";
import { ContextSection } from "@/components/domain/context-section";
import type { StrategySpec } from "@/types/strategy";
import { INPUT_CLASS } from "./spec-fields";

interface SignalExpressionsEditorProps {
	readonly spec: StrategySpec;
	/** 工作副本更新器（与 `useStrategyStudioStore.updateSpec` 同构）。 */
	readonly onChange: (updater: (draft: StrategySpec) => StrategySpec) => void;
}

/**
 * 新增信号的默认表达式占位（与 `ConstraintsPipeline.NEW_CONSTRAINT` 同模式）。
 * 新增对配对权重默认 0（中性），由用户随后编辑。
 */
const NEW_SIGNAL_EXPRESSION = "new_signal";

/** React key for a signal pair（前缀 + 索引；与 `ConstraintsPipeline.constraintKey` 同模式）。 */
function signalKey(index: number): string {
	return `signal-${index}`;
}

/**
 * 信号表达式编辑器：管理 `{expression, weight}` **耦合对**。
 *
 * legacy spec 中 `signal_expressions` 与 `signal_weights` 长度耦合（后端校验等长），
 * 因此增删/重排必须**原子地**同时作用于两个数组（单次 `onChange` 上抛），编辑单个
 * 表达式或权重只改对应槽位。组件把两个平行数组呈现为成对行：表达式输入 + 权重数值
 * 输入 + 上移/下移/删除。
 */
export function SignalExpressionsEditor({ spec, onChange }: SignalExpressionsEditorProps): ReactElement {
	const expressions = spec.signalExpressions;
	const weights = spec.signalWeights;

	/** 同时改写两个数组，保证长度耦合不变（单次更新）。 */
	function updateBoth(nextExpressions: readonly string[], nextWeights: readonly number[]): void {
		onChange((draft) => ({ ...draft, signalExpressions: nextExpressions, signalWeights: nextWeights }));
	}

	return (
		<ContextSection title="信号表达式" count={expressions.length}>
			<div className="flex flex-col gap-(--section-gap) p-(--density-panel-padding)">
				{expressions.length === 0 ? (
					<p className="text-xs text-(--color-foreground-tertiary)">暂无信号表达式</p>
				) : (
					<ul className="flex flex-col gap-1">
						{expressions.map((expression, index) => {
							const weight = weights[index] ?? 0;
							return (
								<li
									key={signalKey(index)}
									className="flex items-center gap-2 rounded-sm p-(--density-panel-padding) transition-colors hover:bg-(--color-interaction-hover-subtle-bg)"
								>
									<input
										aria-label={`信号表达式 ${index + 1}`}
										className={`${INPUT_CLASS} flex-1`}
										value={expression}
										onChange={(event) => {
											const nextValue = event.target.value;
											onChange((draft) => ({
												...draft,
												signalExpressions: draft.signalExpressions.map((value, i) => (i === index ? nextValue : value)),
											}));
										}}
									/>
									<input
										aria-label={`权重 ${index + 1}`}
										className={`${INPUT_CLASS} w-20`}
										inputMode="decimal"
										type="number"
										value={Number.isFinite(weight) ? weight : 0}
										onChange={(event) => {
											const parsed = Number(event.target.value);
											onChange((draft) => ({
												...draft,
												signalWeights: draft.signalWeights.map((value, i) =>
													i === index ? (Number.isFinite(parsed) ? parsed : 0) : value,
												),
											}));
										}}
									/>
									<button
										type="button"
										aria-label={`上移信号 ${index + 1}`}
										disabled={index === 0}
										onClick={() => {
											const nextExpr = [...expressions];
											const nextWeight = [...weights];
											[nextExpr[index], nextExpr[index - 1]] = [nextExpr[index - 1], nextExpr[index]];
											[nextWeight[index], nextWeight[index - 1]] = [nextWeight[index - 1], nextWeight[index]];
											updateBoth(nextExpr, nextWeight);
										}}
										className="rounded-sm px-2 py-0.5 text-xs text-(--color-foreground-secondary) hover:bg-(--color-interaction-hover-subtle-bg) disabled:opacity-40"
									>
										上移
									</button>
									<button
										type="button"
										aria-label={`下移信号 ${index + 1}`}
										disabled={index === expressions.length - 1}
										onClick={() => {
											const nextExpr = [...expressions];
											const nextWeight = [...weights];
											[nextExpr[index], nextExpr[index + 1]] = [nextExpr[index + 1], nextExpr[index]];
											[nextWeight[index], nextWeight[index + 1]] = [nextWeight[index + 1], nextWeight[index]];
											updateBoth(nextExpr, nextWeight);
										}}
										className="rounded-sm px-2 py-0.5 text-xs text-(--color-foreground-secondary) hover:bg-(--color-interaction-hover-subtle-bg) disabled:opacity-40"
									>
										下移
									</button>
									<button
										type="button"
										aria-label={`删除信号 ${index + 1}`}
										onClick={() =>
											updateBoth(
												expressions.filter((_, i) => i !== index),
												weights.filter((_, i) => i !== index),
											)
										}
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
					onClick={() => updateBoth([...expressions, NEW_SIGNAL_EXPRESSION], [...weights, 0])}
					className="self-start rounded-sm bg-(--brand-accent) px-3 py-1 text-sm text-white transition-colors hover:bg-(--brand-accent-hover)"
				>
					添加信号
				</button>
			</div>
		</ContextSection>
	);
}
