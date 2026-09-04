import { useParams } from "@tanstack/react-router";
import { useEffect, useRef, useState } from "react";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { StatusBadge } from "@/components/status/status-badge/status-badge";
import { Button } from "@/components/ui/button";
import { ShellHeaderExtension, StatusBar, StudioLayout } from "@/features/shell";
import { ApiError } from "@/lib/api-client";
import type { NodeDescriptorView, SpecValidation } from "@/types/strategy";
import { serializeStrategySpec } from "../api/mappers";
import { addDescriptorNode } from "../api/pipeline-model";
import {
	useNodeDescriptors,
	useStrategy,
	useStrategyAuthorPreview,
	useStrategySave,
	useStrategyValidation,
	useStrategyVersions,
} from "../hooks";
import { selectIsDirty, useStrategyStudioStore } from "../state/strategy-studio-store";
import { NodeLibrary } from "./node-library";
import { StrategyEditor } from "./strategy-editor";
import { StrategyStudioInspector } from "./strategy-studio-inspector";
import { StrategyStudioLogs } from "./strategy-studio-logs";
import { type StrategyStudioOverlay, StrategyStudioOverlays } from "./strategy-studio-overlays";
import { StudioModeBar } from "./studio-mode-bar";

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
	const detail = useStrategy(strategyId);
	const { data } = detail;
	const versions = useStrategyVersions(strategyId);
	const descriptorsQuery = useNodeDescriptors();
	const validate = useStrategyValidation();
	const authorPreview = useStrategyAuthorPreview();
	const save = useStrategySave();
	const [validation, setValidation] = useState<SpecValidation | null>(null);
	const [validatedPayload, setValidatedPayload] = useState<string | null>(null);
	const [authorPreviewPayload, setAuthorPreviewPayload] = useState<string | null>(null);
	const [overlay, setOverlay] = useState<StrategyStudioOverlay | null>(null);
	const [operationNotice, setOperationNotice] = useState<string | null>(null);
	const saveAttemptRef = useRef<{ readonly payload: string; readonly key: string } | null>(null);

	const workingSpec = useStrategyStudioStore((s) => s.workingSpec);
	const mode = useStrategyStudioStore((s) => s.mode);
	const selectedNodeKey = useStrategyStudioStore((s) => s.selectedNodeKey);
	const loadSpec = useStrategyStudioStore((s) => s.loadSpec);
	const updateSpec = useStrategyStudioStore((s) => s.updateSpec);
	const selectNode = useStrategyStudioStore((s) => s.selectNode);
	const setMode = useStrategyStudioStore((s) => s.setMode);
	const isDirty = useStrategyStudioStore(selectIsDirty);
	const currentVersion = versions.data?.find((version) => version.version === data?.version);
	const breadcrumbs = ["研究", "策略", data ? `${strategyId} · v${data.version}` : strategyId] as const;

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
			setAuthorPreviewPayload(null);
			setOperationNotice(null);
			saveAttemptRef.current = null;
		}
	}, [data, loadSpec]);

	const currentPayload = workingSpec ? JSON.stringify(serializeStrategySpec(workingSpec)) : null;
	const validationIsStale = validation !== null && currentPayload !== validatedPayload;
	const authorPreviewIsStale = authorPreview.data !== undefined && currentPayload !== authorPreviewPayload;

	function handleAuthorPreview() {
		if (!workingSpec || !data) return;
		const specJson = serializeStrategySpec(workingSpec);
		const payloadIdentity = JSON.stringify(specJson);
		setOverlay("author-preview");
		authorPreview.mutate(
			{
				strategyId,
				version: data.version,
				payload: {
					spec_json: specJson,
					expressions: workingSpec.signalExpressions.map((expression, index) => ({
						derived_id: /^[A-Za-z_][A-Za-z0-9_]*$/.test(expression) ? expression : `author_expression_${index + 1}`,
						version: 1,
						expression,
					})),
				},
			},
			{
				onSuccess: () => setAuthorPreviewPayload(payloadIdentity),
			},
		);
	}

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
					setOperationNotice(null);
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
				onSuccess: (savedDetail) => {
					saveAttemptRef.current = null;
					setOverlay(null);
					setOperationNotice(`已保存为新版本 v${savedDetail.version}`);
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

	const mutationErrorMessage = mutationError(validate.error) ?? mutationError(save.error);
	const authorPreviewError = mutationError(authorPreview.error);
	const saveReady = Boolean(isDirty && validation?.valid && !validationIsStale && !save.isPending);

	return (
		<section aria-label="策略 Studio 工作区" className="h-full min-h-0">
			<ShellHeaderExtension>
				<div
					className="ml-auto flex min-w-0 items-center gap-1.5"
					data-info-level="l1"
					data-info-unit="strategy-header"
				>
					{data && (
						<div className="mr-1 hidden min-w-0 items-center gap-2 border-r border-(--color-border-subtle) pr-3 2xl:flex">
							<span className="max-w-44 truncate text-xs font-medium text-(--color-foreground-secondary)">
								{data.name} · v{data.version}
							</span>
							<StatusBadge
								variant={data.lifecycleState === "deprecated" ? "default" : "healthy"}
								label={data.lifecycleState}
								size="sm"
							/>
						</div>
					)}
					<Button size="sm" variant="outline" onClick={handleValidate} disabled={!workingSpec || validate.isPending}>
						{validate.isPending ? "校验中…" : "校验"}
					</Button>
					<Button
						size="sm"
						variant="outline"
						onClick={handleAuthorPreview}
						disabled={!workingSpec || !data || authorPreview.isPending}
					>
						{authorPreview.isPending ? "Author 运行中…" : "Author 预览"}
					</Button>
					<Button size="sm" onClick={() => setOverlay("save")} disabled={!saveReady}>
						保存
					</Button>
					<Button size="sm" variant="outline" onClick={() => setOverlay("dry-run")} disabled={!data}>
						Dry Run
					</Button>
					<Button size="sm" variant="outline" onClick={() => setOverlay("backtest")} disabled={!data}>
						提交回测
					</Button>
					<Button
						size="sm"
						variant="destructive"
						onClick={() => setOverlay("deprecate")}
						disabled={!data || data.lifecycleState === "deprecated"}
					>
						弃用版本
					</Button>
				</div>
			</ShellHeaderExtension>
			<StudioLayout
				className={
					'grid-cols-[220px_minmax(0,1fr)_300px] grid-rows-[36px_minmax(0,1fr)_132px] pb-(--height-status-bar) max-[1280px]:grid-cols-[200px_minmax(0,1fr)_280px] max-[899px]:h-auto max-[899px]:overflow-auto max-[899px]:grid-cols-1 max-[899px]:grid-rows-[auto_auto_auto_auto_auto] max-[899px]:[grid-template-areas:"modes""sources""main""inspector""logs"]'
				}
				modes={
					<div data-info-level="l1" data-info-unit="studio-mode-bar" className="h-9">
						<StudioModeBar
							modes={STUDIO_MODES}
							activeMode={mode}
							onModeChange={handleModeChange}
							breadcrumbs={breadcrumbs}
						/>
					</div>
				}
				source={
					<div
						data-info-level="l1"
						data-info-unit="node-library"
						className="h-full overflow-y-auto border-r border-(--color-border-subtle) bg-(--color-surface-1)"
					>
						<NodeLibrary onAdd={handleAddDescriptor} onPreviewFactors={() => setOverlay("factor-preview")} />
					</div>
				}
				main={
					<div className="h-full overflow-y-auto bg-(--color-surface-app) p-(--density-panel-padding)">
						<div data-info-level="l1" data-info-unit="strategy-editor">
							{detail.isLoading ? (
								<LoadingSkeleton variant="panel" />
							) : detail.error ? (
								<div className="rounded-(--radius-md) border border-(--color-led-danger) p-4 text-sm">
									<p role="alert" className="text-(--color-led-danger)">
										{mutationError(detail.error)}
									</p>
									<Button variant="outline" size="sm" className="mt-3" onClick={() => void detail.refetch()}>
										重试策略定义
									</Button>
								</div>
							) : !data ? (
								<p className="p-4 text-sm text-(--color-foreground-tertiary)">策略不存在或服务端未返回定义。</p>
							) : workingSpec ? (
								<StrategyEditor
									spec={workingSpec}
									mode={mode}
									descriptors={descriptorsQuery.data ?? []}
									selectedKey={selectedNodeKey}
									onChange={updateSpec}
									onSelect={selectNode}
								/>
							) : (
								<LoadingSkeleton variant="panel" />
							)}
						</div>
					</div>
				}
				inspector={
					<div
						data-info-level="l2"
						data-info-unit="strategy-inspector"
						className="h-full overflow-y-auto border-l border-(--color-border-subtle) bg-(--color-surface-1)"
					>
						{workingSpec && data ? (
							<StrategyStudioInspector
								detail={data}
								spec={workingSpec}
								specHash={currentVersion?.specHash ?? null}
								descriptors={descriptorsQuery.data ?? []}
								selectedKey={selectedNodeKey}
								onChange={updateSpec}
								validation={validation}
								validationIsStale={validationIsStale}
							/>
						) : (
							<LoadingSkeleton />
						)}
					</div>
				}
				logs={
					<div data-info-level="l2" data-info-unit="validation-panel">
						<StrategyStudioLogs
							isDirty={isDirty}
							isSaving={save.isPending}
							isValidating={validate.isPending}
							mutationError={
								mutationErrorMessage
									? `${mutationErrorMessage}${
											save.error instanceof ApiError && save.error.status === 503
												? "。结果未知，重试将复用同一 Idempotency-Key。"
												: ""
										}`
									: null
							}
							operationNotice={operationNotice}
							validation={validation}
							validationIsStale={validationIsStale}
						/>
					</div>
				}
			/>
			{validation && !validationIsStale && (
				<div
					role="status"
					aria-label="Spec 校验结果"
					className="fixed top-[calc(var(--height-header)+12px)] right-4 z-40 rounded-(--radius-md) border border-(--color-border) bg-(--color-surface-3) px-3 py-2 text-xs shadow-lg"
				>
					<span className={validation.valid ? "text-(--color-led-success)" : "text-(--color-led-danger)"}>
						{validation.valid ? "校验有效" : "校验未通过"}
					</span>
					<code className="ml-2 font-data text-(--color-foreground-tertiary)">{validation.canonicalHash}</code>
				</div>
			)}
			<StrategyStudioOverlays
				open={overlay}
				onClose={() => setOverlay(null)}
				strategyId={strategyId}
				detail={data}
				workingSpec={workingSpec}
				authorPreview={authorPreview.data ?? null}
				authorPreviewError={authorPreviewError}
				authorPreviewIsPending={authorPreview.isPending}
				authorPreviewIsStale={authorPreviewIsStale}
				validation={validation}
				validationIsStale={validationIsStale}
				isSaving={save.isPending}
				onConfirmSave={handleSave}
				onOperation={setOperationNotice}
			/>
			<StatusBar />
		</section>
	);
}
