import { useParams } from "@tanstack/react-router";
import { useEffect, useRef, useState } from "react";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { StatusBar, StudioLayout } from "@/features/shell";
import { ApiError } from "@/lib/api-client";
import type { NodeDescriptorView, SpecValidation } from "@/types/strategy";
import { serializeStrategySpec } from "../api/mappers";
import { addDescriptorNode } from "../api/pipeline-model";
import { useNodeDescriptors, useStrategy, useStrategySave, useStrategyValidation } from "../hooks";
import { selectIsDirty, useStrategyStudioStore } from "../state/strategy-studio-store";
import { NodeLibrary } from "./node-library";
import { StrategyEditor } from "./strategy-editor";
import { StrategyHeader } from "./strategy-header";
import { NodeInspector } from "./strategy-inspector";
import { StudioModeBar } from "./studio-mode-bar";
import { ValidationPanel } from "./validation-panel";

const STUDIO_MODES = [
	{ id: "form", label: "Form" },
	{ id: "pipeline", label: "Pipeline" },
] as const;

const DEFAULT_STRATEGY_ID = "seed_etf_industry_rotation";

function createSaveIdempotencyKey(): string {
	const randomId = globalThis.crypto?.randomUUID?.();
	return `strategy-save-${randomId ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`}`;
}

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
	const descriptorsQuery = useNodeDescriptors();
	const validate = useStrategyValidation();
	const save = useStrategySave();
	const [validation, setValidation] = useState<SpecValidation | null>(null);
	const [validatedPayload, setValidatedPayload] = useState<string | null>(null);
	const saveAttemptRef = useRef<{ readonly payload: string; readonly key: string } | null>(null);

	const workingSpec = useStrategyStudioStore((s) => s.workingSpec);
	const mode = useStrategyStudioStore((s) => s.mode);
	const selectedNodeKey = useStrategyStudioStore((s) => s.selectedNodeKey);
	const loadSpec = useStrategyStudioStore((s) => s.loadSpec);
	const updateSpec = useStrategyStudioStore((s) => s.updateSpec);
	const selectNode = useStrategyStudioStore((s) => s.selectNode);
	const setMode = useStrategyStudioStore((s) => s.setMode);
	const isDirty = useStrategyStudioStore(selectIsDirty);

	function handleModeChange(modeId: string): void {
		if (modeId === "form" || modeId === "pipeline") {
			setMode(modeId);
		}
	}

	const loadedVersionRef = useRef<string | null>(null);
	useEffect(() => {
		const identity = data ? `${data.strategyId}@${data.version}` : null;
		if (data && identity !== loadedVersionRef.current) {
			loadedVersionRef.current = identity;
			loadSpec(data.spec);
			setValidation(null);
			setValidatedPayload(null);
			saveAttemptRef.current = null;
		}
	}, [data, loadSpec]);

	const currentPayload = workingSpec ? JSON.stringify(serializeStrategySpec(workingSpec)) : null;
	const validationIsStale = validation !== null && currentPayload !== validatedPayload;

	function handleValidate() {
		if (!workingSpec || !data) return;
		const specJson = serializeStrategySpec(workingSpec);
		const payload = JSON.stringify(specJson);
		validate.mutate(
			{ strategyId, version: data.version, specJson },
			{
				onSuccess: (result) => {
					setValidation(result);
					setValidatedPayload(payload);
				},
			},
		);
	}

	function handleSave() {
		if (!workingSpec || !data) return;
		if (!validation || validationIsStale || !validation.valid) return;
		const payload = currentPayload ?? "";
		const existing = saveAttemptRef.current;
		const key = existing?.payload === payload ? existing.key : createSaveIdempotencyKey();
		saveAttemptRef.current = { payload, key };
		save.mutate(
			{
				strategyId,
				version: data.version,
				spec: workingSpec,
				name: workingSpec.name,
				tags: data.tags,
				idempotencyKey: key,
			},
			{
				onSuccess: () => {
					saveAttemptRef.current = null;
				},
			},
		);
	}

	function handleAddDescriptor(descriptor: NodeDescriptorView): void {
		updateSpec((draft) => addDescriptorNode(draft, descriptor));
		setMode("pipeline");
	}

	function mutationError(error: Error | null): string | null {
		if (!error) return null;
		if (error instanceof ApiError)
			return `${error.status} ${error.errorCode ?? "STRATEGY_MUTATION_ERROR"}: ${error.message}`;
		return error.message;
	}

	return (
		<>
			<StudioLayout
				className={
					'pb-(--height-status-bar) max-[899px]:h-auto max-[899px]:overflow-auto max-[899px]:grid-cols-1 max-[899px]:grid-rows-[auto_auto_auto_auto] max-[899px]:[grid-template-areas:"modes""sources""main""inspector"]'
				}
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
						<NodeLibrary onAdd={handleAddDescriptor} />
					</div>
				}
				main={
					<div className="flex flex-col gap-(--section-gap)">
						<div data-info-level="l1" data-info-unit="strategy-header">
							<StrategyHeader id={strategyId} />
						</div>
						<div data-info-level="l1" data-info-unit="strategy-editor">
							{workingSpec ? (
								<StrategyEditor
									spec={workingSpec}
									mode={mode}
									descriptors={descriptorsQuery.data ?? []}
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
								<ValidationPanel
									validation={validation}
									isValidating={validate.isPending}
									isStale={validationIsStale}
								/>
								{mutationError(validate.error) && (
									<p role="alert" className="text-sm text-(--color-led-danger)">
										{mutationError(validate.error)}
									</p>
								)}
								{mutationError(save.error) && (
									<p role="alert" className="text-sm text-(--color-led-danger)">
										{mutationError(save.error)}
										{save.error instanceof ApiError && save.error.status === 503
											? "。结果未知，重试将复用同一 Idempotency-Key。"
											: ""}
									</p>
								)}
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
										disabled={!isDirty || save.isPending || !validation?.valid || validationIsStale}
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
							<NodeInspector
								spec={workingSpec}
								descriptors={descriptorsQuery.data ?? []}
								selectedKey={selectedNodeKey}
								onChange={updateSpec}
							/>
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
