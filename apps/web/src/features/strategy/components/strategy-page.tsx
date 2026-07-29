import { useParams } from "@tanstack/react-router";
import { useEffect, useRef, useState } from "react";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { StatusBar, StudioLayout } from "@/features/shell";
import type { SpecValidation } from "@/types/strategy";
import { serializeStrategySpec } from "../api/mappers";
import { useStrategy, useStrategySave, useStrategyValidation } from "../hooks";
import { selectIsDirty, useStrategyStudioStore } from "../state/strategy-studio-store";
import { NodeLibrary } from "./node-library";
import { StrategyEditor } from "./strategy-editor";
import { StrategyHeader } from "./strategy-header";
import { NodeInspector } from "./strategy-inspector";
import { StudioModeBar } from "./studio-mode-bar";
import { ValidationPanel } from "./validation-panel";

const STUDIO_MODES = [
	{ id: "form", label: "Form Builder" },
	{ id: "code", label: "Code Editor" },
] as const;

const DEFAULT_STRATEGY_ID = "seed_etf_industry_rotation";

/**
 * Strategy Studio 页（编辑器编排层）。
 *
 * 服务端真理由 `useStrategy` 持有；编辑工作副本由 `useStrategyStudioStore` 持有。
 * `loadSpec` 仅在 version 变化时触发（`loadedVersionRef` 守卫），避免编辑中 refetch 覆盖。
 */
export function StrategyPage() {
	const { id } = useParams({ strict: false }) as { id?: string };
	const strategyId = id ?? DEFAULT_STRATEGY_ID;
	const breadcrumbs = ["研究", "策略", strategyId] as const;

	const { data } = useStrategy(strategyId);
	const validate = useStrategyValidation();
	const save = useStrategySave();
	const [validation, setValidation] = useState<SpecValidation | null>(null);

	const workingSpec = useStrategyStudioStore((s) => s.workingSpec);
	const mode = useStrategyStudioStore((s) => s.mode);
	const selectedNodeKey = useStrategyStudioStore((s) => s.selectedNodeKey);
	const loadSpec = useStrategyStudioStore((s) => s.loadSpec);
	const updateSpec = useStrategyStudioStore((s) => s.updateSpec);
	const selectNode = useStrategyStudioStore((s) => s.selectNode);
	const setMode = useStrategyStudioStore((s) => s.setMode);
	const isDirty = useStrategyStudioStore(selectIsDirty);

	function handleModeChange(modeId: string): void {
		if (modeId === "form" || modeId === "code") {
			setMode(modeId);
		}
	}

	const loadedVersionRef = useRef<number | null>(null);
	useEffect(() => {
		if (data && data.version !== loadedVersionRef.current) {
			loadedVersionRef.current = data.version;
			loadSpec(data.spec);
		}
	}, [data, loadSpec]);

	function handleValidate() {
		if (!workingSpec || !data) return;
		validate.mutate(
			{ strategyId, version: data.version, specJson: serializeStrategySpec(workingSpec) },
			{ onSuccess: setValidation },
		);
	}

	function handleSave() {
		if (!workingSpec || !data) return;
		save.mutate({
			strategyId,
			version: data.version,
			spec: workingSpec,
			name: workingSpec.name,
			tags: data.tags,
		});
	}

	return (
		<>
			<StudioLayout
				className="pb-(--height-status-bar)"
				modes={
					<div data-info-level="l1" data-info-unit="studio-mode-bar">
						<StudioModeBar
							modes={STUDIO_MODES}
							activeMode={mode}
							onModeChange={handleModeChange}
							breadcrumbs={breadcrumbs}
						/>
					</div>
				}
				source={
					<div data-info-level="l1" data-info-unit="node-library">
						<NodeLibrary />
					</div>
				}
				main={
					<div className="flex flex-col gap-(--section-gap)">
						<div data-info-level="l1" data-info-unit="strategy-header">
							<StrategyHeader id={strategyId} />
						</div>
						<div data-info-level="l1" data-info-unit="strategy-code">
							{workingSpec ? (
								<StrategyEditor
									spec={workingSpec}
									mode={mode}
									selectedKey={selectedNodeKey}
									onChange={updateSpec}
									onSelect={selectNode}
								/>
							) : (
								<LoadingSkeleton />
							)}
						</div>
						<div data-info-level="l2" data-info-unit="validation-panel">
							<div className="flex flex-col gap-2 p-(--density-panel-padding)">
								{isDirty && <span className="text-xs text-(--color-foreground-tertiary)">● 未保存的编辑</span>}
								<ValidationPanel validation={validation} isValidating={validate.isPending} />
								<div className="flex gap-2 self-start">
									<button
										type="button"
										onClick={handleValidate}
										disabled={!workingSpec || validate.isPending}
										className="rounded-sm bg-(--brand-accent) px-3 py-1 text-sm text-white transition-colors hover:bg-(--brand-accent-hover) disabled:opacity-50"
									>
										校验 Spec
									</button>
									<button
										type="button"
										onClick={handleSave}
										disabled={!isDirty || save.isPending}
										className="rounded-sm bg-(--brand-accent) px-3 py-1 text-sm text-white transition-colors hover:bg-(--brand-accent-hover) disabled:opacity-50"
									>
										{save.isPending ? "保存中…" : "保存为新版本"}
									</button>
								</div>
							</div>
						</div>
					</div>
				}
				inspector={
					<div data-info-level="l2" data-info-unit="strategy-inspector">
						{workingSpec ? (
							<NodeInspector spec={workingSpec} selectedKey={selectedNodeKey} onChange={updateSpec} />
						) : (
							<LoadingSkeleton />
						)}
					</div>
				}
			/>
			<StatusBar />
		</>
	);
}
