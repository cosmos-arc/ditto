import type { ReactElement } from "react";
import { ContextSection } from "@/components/domain/context-section";
import { serializeStrategySpec } from "@/features/strategy/api/mappers";
import type { StrategySpec } from "@/types/strategy";
import type { StudioMode } from "../state/strategy-studio-store";
import { ParamConstraintsEditor } from "./param-constraints-editor";
import { SignalExpressionsEditor } from "./signal-expressions-editor";
import { ConstraintsPipeline } from "./strategy-pipeline-view";
import { StrategySpecForm } from "./strategy-spec-form";

interface StrategyEditorProps {
	readonly spec: StrategySpec;
	readonly mode: StudioMode;
	readonly selectedKey: string | null;
	readonly onChange: (updater: (draft: StrategySpec) => StrategySpec) => void;
	readonly onSelect: (key: string | null) => void;
}

/**
 * 策略编辑容器（Studio main 区域）。
 *
 * `form` 模式：{@link StrategySpecForm}（标量 + 单例槽位）+ {@link ConstraintsPipeline}
 * （约束 CRUD）+ {@link SignalExpressionsEditor}（信号/权重耦合对）+
 * {@link ParamConstraintsEditor}（参数约束 CRUD）。`code` 模式：serialize 后的 legacy
 * spec_json 只读预览（与后端存储形态一致）。工作副本与选中态由 `useStrategyStudioStore`
 * 持有，由 StrategyPage 注入。
 */
export function StrategyEditor({ spec, mode, selectedKey, onChange, onSelect }: StrategyEditorProps): ReactElement {
	if (mode === "code") {
		return (
			<ContextSection title="Spec JSON（只读）">
				<pre className="overflow-auto p-(--density-panel-padding) text-xs text-(--color-foreground-tertiary)">
					<code>{JSON.stringify(serializeStrategySpec(spec), null, 2)}</code>
				</pre>
			</ContextSection>
		);
	}

	return (
		<div className="flex flex-col gap-(--section-gap)">
			<StrategySpecForm spec={spec} onChange={onChange} />
			<ConstraintsPipeline
				constraints={spec.constraints}
				onChange={onChange}
				onSelect={onSelect}
				selectedKey={selectedKey}
			/>
			<SignalExpressionsEditor spec={spec} onChange={onChange} />
			<ParamConstraintsEditor spec={spec} onChange={onChange} />
		</div>
	);
}
