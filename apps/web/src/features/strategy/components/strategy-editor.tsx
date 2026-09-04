import type { ReactElement } from "react";
import type { NodeDescriptorView, StrategySpec } from "@/types/strategy";
import type { StudioMode } from "../state/strategy-studio-store";
import { ParamConstraintsEditor } from "./param-constraints-editor";
import { SignalExpressionsEditor } from "./signal-expressions-editor";
import { ConstraintsPipeline } from "./strategy-pipeline-view";
import { StrategySpecForm } from "./strategy-spec-form";

interface StrategyEditorProps {
	readonly spec: StrategySpec;
	readonly mode: StudioMode;
	readonly descriptors: readonly NodeDescriptorView[];
	readonly selectedKey: string | null;
	readonly onChange: (updater: (draft: StrategySpec) => StrategySpec) => void;
	readonly onSelect: (key: string | null) => void;
}

/**
 * 策略编辑容器（Studio main 区域）。
 *
 * `form` 模式编辑 legacy 表单；`pipeline` 模式只通过 descriptor registry 展示和编辑
 * 固定语法节点。两种模式共享同一 working spec，最终都交给 backend validate 生成 hash。
 */
export function StrategyEditor({
	spec,
	mode,
	descriptors,
	selectedKey,
	onChange,
	onSelect,
}: StrategyEditorProps): ReactElement {
	if (mode === "pipeline") {
		return (
			<ConstraintsPipeline
				spec={spec}
				descriptors={descriptors}
				onChange={onChange}
				onSelect={onSelect}
				selectedKey={selectedKey}
			/>
		);
	}

	return (
		<div className="grid grid-cols-1 gap-3 2xl:grid-cols-2">
			<div className="2xl:col-span-2">
				<StrategySpecForm spec={spec} onChange={onChange} />
			</div>
			<SignalExpressionsEditor spec={spec} onChange={onChange} />
			<ParamConstraintsEditor spec={spec} onChange={onChange} />
		</div>
	);
}
