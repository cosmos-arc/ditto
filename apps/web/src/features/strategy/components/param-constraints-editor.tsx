import type { ReactElement } from "react";
import { ContextSection } from "@/components/domain/context-section";
import type { ParamConstraintSpec, ParamDtype, StrategySpec } from "@/types/strategy";
import { INPUT_CLASS } from "./spec-fields";

interface ParamConstraintsEditorProps {
	readonly spec: StrategySpec;
	/** 工作副本更新器（与 `useStrategyStudioStore.updateSpec` 同构）。 */
	readonly onChange: (updater: (draft: StrategySpec) => StrategySpec) => void;
}

const DTYPE_OPTIONS: readonly ParamDtype[] = ["bool", "int", "float", "str"];

/** React key for a constraint row（前缀 + 索引；与 `ConstraintsPipeline.constraintKey` 同模式）。 */
function paramKey(index: number): string {
	return `param-${index}`;
}

/** 数值型 dtype（min/max/step 仅对 int/float 有意义）。 */
function isNumericDtype(dtype: ParamDtype): boolean {
	return dtype === "int" || dtype === "float";
}

/**
 * 把 `allowedValues` 数组渲染为逗号分隔文本（与编辑输入框双向对应）。
 * `"fast, slow"` ← `["fast", "slow"]`。
 */
function joinAllowedValues(values: readonly string[]): string {
	return values.join(", ");
}

/**
 * 把逗号分隔文本切回字符串数组：按 `,` 拆分、去空白、丢空段。
 * `"x, y ,z,"` → `["x", "y", "z"]`。
 */
function splitAllowedValues(text: string): string[] {
	return text
		.split(",")
		.map((segment) => segment.trim())
		.filter((segment) => segment.length > 0);
}

/**
 * 参数约束编辑器：`param_constraints` 数组的字段级 CRUD。
 *
 * 每行编辑 `name` / `dtype`（bool/int/float/str）/ 可选 `min/max/step`（仅 int/float
 * 显示）/ `allowedValues`（逗号分隔）。增删/重排复用 `ConstraintsPipeline` 的按钮模式。
 *
 * 注意：后端 `inject_template_constraints` 在 `param_constraints` 为空且模板已知时会用
 * 模板约束覆盖；一旦此处编辑使数组非空，反序列化时不再注入。前端无需特殊处理，但编辑后
 * 的非空约束会被原样保存与参与 canonical hash。
 */
export function ParamConstraintsEditor({ spec, onChange }: ParamConstraintsEditorProps): ReactElement {
	const constraints = spec.paramConstraints;

	function patchAt(index: number, patch: Partial<ParamConstraintSpec>): void {
		onChange((draft) => ({
			...draft,
			paramConstraints: draft.paramConstraints.map((constraint, i) =>
				i === index ? { ...constraint, ...patch } : constraint,
			),
		}));
	}
	function move(from: number, to: number): void {
		onChange((draft) => {
			const next = [...draft.paramConstraints];
			[next[from], next[to]] = [next[to], next[from]];
			return { ...draft, paramConstraints: next };
		});
	}

	return (
		<ContextSection title="参数约束" count={constraints.length}>
			<div className="flex flex-col gap-(--section-gap) p-(--density-panel-padding)">
				{constraints.length === 0 ? (
					<p className="text-xs text-(--color-foreground-tertiary)">暂无参数约束</p>
				) : (
					<ul className="flex flex-col gap-1">
						{constraints.map((constraint, index) => {
							const showNumeric = isNumericDtype(constraint.dtype);
							return (
								<li
									key={paramKey(index)}
									className="flex flex-col gap-2 rounded-sm p-(--density-panel-padding) transition-colors hover:bg-(--color-interaction-hover-subtle-bg)"
								>
									<div className="flex items-center gap-2">
										<input
											aria-label={`参数名 ${index + 1}`}
											className={`${INPUT_CLASS} flex-1`}
											value={constraint.name}
											onChange={(event) => patchAt(index, { name: event.target.value })}
										/>
										<select
											aria-label={`类型 ${index + 1}`}
											className={INPUT_CLASS}
											value={constraint.dtype}
											onChange={(event) => patchAt(index, { dtype: event.target.value as ParamDtype })}
										>
											{DTYPE_OPTIONS.map((option) => (
												<option key={option} value={option}>
													{option}
												</option>
											))}
										</select>
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
											onClick={() =>
												onChange((draft) => ({
													...draft,
													paramConstraints: draft.paramConstraints.filter((_, i) => i !== index),
												}))
											}
											className="rounded-sm px-2 py-0.5 text-xs text-(--color-led-danger) hover:bg-(--color-interaction-hover-subtle-bg)"
										>
											删除
										</button>
									</div>
									{showNumeric && (
										<div className="flex items-center gap-2">
											<label className="flex flex-col gap-1 text-(length:--text-sm)">
												<span className="text-(--color-foreground-secondary)">最小值 {index + 1}</span>
												<input
													aria-label={`最小值 ${index + 1}`}
													className={INPUT_CLASS}
													inputMode="decimal"
													type="number"
													value={constraint.minValue ?? 0}
													onChange={(event) => {
														const parsed = Number(event.target.value);
														patchAt(index, { minValue: Number.isFinite(parsed) ? parsed : 0 });
													}}
												/>
											</label>
											<label className="flex flex-col gap-1 text-(length:--text-sm)">
												<span className="text-(--color-foreground-secondary)">最大值 {index + 1}</span>
												<input
													aria-label={`最大值 ${index + 1}`}
													className={INPUT_CLASS}
													inputMode="decimal"
													type="number"
													value={constraint.maxValue ?? 0}
													onChange={(event) => {
														const parsed = Number(event.target.value);
														patchAt(index, { maxValue: Number.isFinite(parsed) ? parsed : 0 });
													}}
												/>
											</label>
											<label className="flex flex-col gap-1 text-(length:--text-sm)">
												<span className="text-(--color-foreground-secondary)">步长 {index + 1}</span>
												<input
													aria-label={`步长 ${index + 1}`}
													className={INPUT_CLASS}
													inputMode="decimal"
													type="number"
													value={constraint.step ?? 0}
													onChange={(event) => {
														const parsed = Number(event.target.value);
														patchAt(index, { step: Number.isFinite(parsed) ? parsed : 0 });
													}}
												/>
											</label>
										</div>
									)}
									<label className="flex flex-col gap-1 text-(length:--text-sm)">
										<span className="text-(--color-foreground-secondary)">允许值 {index + 1}（逗号分隔）</span>
										<input
											aria-label={`允许值 ${index + 1}`}
											className={INPUT_CLASS}
											value={joinAllowedValues(constraint.allowedValues)}
											onChange={(event) => patchAt(index, { allowedValues: splitAllowedValues(event.target.value) })}
										/>
									</label>
								</li>
							);
						})}
					</ul>
				)}
				<button
					type="button"
					onClick={() =>
						onChange((draft) => ({
							...draft,
							paramConstraints: [...draft.paramConstraints, { name: "", dtype: "int", allowedValues: [] }],
						}))
					}
					className="self-start rounded-sm bg-(--brand-accent) px-3 py-1 text-sm text-white transition-colors hover:bg-(--brand-accent-hover)"
				>
					添加参数约束
				</button>
			</div>
		</ContextSection>
	);
}
