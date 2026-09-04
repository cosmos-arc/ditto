import { useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { AgentContextActions } from "@/features/agent";
import { ShellHeaderExtension, StatusBar, StudioLayout } from "@/features/shell";
import { ApiError } from "@/lib/api-client";
import {
	buildExperimentPlanningRequest,
	createDefaultExperimentDraft,
	type ExperimentConfigDraft,
	type ExperimentPlanningRequest,
	estimateCandidateCount,
	planningRequestIdentity,
} from "../api/experiments";
import { useExperimentLaunch, useExperimentPreflight } from "../hooks";
import { ExperimentConfigForm } from "./experiment-config-form";
import { ExperimentPreflightPanel } from "./experiment-preflight-panel";

interface ExperimentCreatePageProps {
	readonly onLaunched?: (experimentId: string) => void;
}

const PLANNING_SECTIONS = [
	"Experiment identity",
	"Frozen strategy and snapshot",
	"Validation and promotion",
	"Candidate matrix",
	"Data, cost and execution policy",
] as const;

function commandKey(): string {
	const randomId = globalThis.crypto?.randomUUID?.();
	return `experiment-launch-${randomId ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`}`;
}

function errorMessage(error: Error | null): string | null {
	if (!error) return null;
	if (error instanceof ApiError) return `${error.status} ${error.errorCode ?? "EXPERIMENT_ERROR"}: ${error.message}`;
	return error.message;
}

function IdentityRow({ label, value }: { readonly label: string; readonly value: string }) {
	return (
		<div className="border-b border-(--color-border-subtle) px-3 py-2 last:border-b-0">
			<span className="block text-xs uppercase tracking-[0.08em] text-(--color-foreground-tertiary)">{label}</span>
			<span className="mt-0.5 block break-all font-data text-xs text-(--color-foreground)">{value}</span>
		</div>
	);
}

export function ExperimentCreatePage({ onLaunched }: ExperimentCreatePageProps) {
	const [draft, setDraft] = useState<ExperimentConfigDraft>(createDefaultExperimentDraft);
	const [preflightIdentity, setPreflightIdentity] = useState<string | null>(null);
	const [confirmed, setConfirmed] = useState(false);
	const [formError, setFormError] = useState<string | null>(null);
	const launchAttempt = useRef<{ readonly identity: string; readonly key: string } | null>(null);
	const preflight = useExperimentPreflight();
	const launch = useExperimentLaunch();

	let planning: ExperimentPlanningRequest | null = null;
	let currentIdentity: string | null = null;
	try {
		planning = buildExperimentPlanningRequest(draft);
		currentIdentity = planningRequestIdentity(planning);
	} catch {
		planning = null;
	}
	const stale = preflight.data !== undefined && currentIdentity !== preflightIdentity;
	const candidateCount = estimateCandidateCount(draft.axesJson);
	const canLaunch = Boolean(
		planning && preflight.data?.planHash && preflight.data.status.toLowerCase() === "ready" && confirmed && !stale,
	);

	function changeDraft(next: ExperimentConfigDraft): void {
		setDraft(next);
		setConfirmed(false);
		setFormError(null);
	}

	function runPreflight(): void {
		if (!planning || !currentIdentity) {
			setFormError("Planning document 包含无效 JSON，无法 preflight。");
			return;
		}
		setFormError(null);
		preflight.mutate(planning, {
			onSuccess: () => {
				setPreflightIdentity(currentIdentity);
				setConfirmed(false);
				launchAttempt.current = null;
			},
		});
	}

	function runLaunch(): void {
		const planHash = preflight.data?.planHash;
		if (!planning || !currentIdentity || !planHash || !canLaunch) return;
		const prior = launchAttempt.current;
		const key = prior?.identity === currentIdentity ? prior.key : commandKey();
		launchAttempt.current = { identity: currentIdentity, key };
		launch.mutate(
			{ planning, confirmedPlanHash: planHash, idempotencyKey: key },
			{
				onSuccess: (receipt) => {
					launchAttempt.current = null;
					onLaunched?.(receipt.experimentId);
				},
			},
		);
	}

	const preflightState = !preflight.data ? "尚未运行" : stale ? "需要重新运行" : preflight.data.status;
	const preflightError = errorMessage(preflight.error);
	const launchError = errorMessage(launch.error);

	return (
		<section aria-label="实验规划工作区" className="h-full min-h-0">
			<ShellHeaderExtension>
				<div
					className="ml-auto flex min-w-0 items-center gap-1.5"
					data-info-level="l1"
					data-info-unit="experiment-create-actions"
				>
					<Button size="sm" variant="outline" onClick={runPreflight} disabled={preflight.isPending}>
						{preflight.isPending ? "Preflight 中…" : "运行只读 Preflight"}
					</Button>
					<Button size="sm" onClick={runLaunch} disabled={!canLaunch || launch.isPending}>
						{launch.isPending ? "启动中…" : "启动实验"}
					</Button>
				</div>
			</ShellHeaderExtension>
			<StudioLayout
				className={
					'grid-cols-[220px_minmax(0,1fr)_300px] grid-rows-[36px_minmax(0,1fr)_132px] pb-(--height-status-bar) max-[1280px]:grid-cols-[200px_minmax(0,1fr)_280px] max-[899px]:h-auto max-[899px]:overflow-auto max-[899px]:grid-cols-1 max-[899px]:grid-rows-[auto_auto_auto_auto_auto] max-[899px]:[grid-template-areas:"modes""sources""main""inspector""logs"]'
				}
				modes={
					<nav
						aria-label="实验规划路径与状态"
						className="flex h-9 items-center gap-2 border-b border-(--color-border-subtle) bg-(--color-surface-strip) px-3 text-xs"
						data-info-level="l1"
						data-info-unit="experiment-mode-bar"
					>
						<span className="text-(--color-foreground-tertiary)">研究</span>
						<span aria-hidden="true" className="text-(--color-foreground-tertiary)">
							/
						</span>
						<span className="text-(--color-foreground-secondary)">实验规划</span>
						<span aria-hidden="true" className="text-(--color-foreground-tertiary)">
							/
						</span>
						<span className="font-medium">Draft</span>
						<span className="ml-auto rounded-full border border-(--color-border-subtle) px-2 py-0.5 font-data text-xs uppercase text-(--color-foreground-tertiary)">
							Preflight · {preflightState}
						</span>
					</nav>
				}
				source={
					<aside
						className="h-full overflow-y-auto border-r border-(--color-border-subtle) bg-(--color-surface-1)"
						data-info-level="l1"
						data-info-unit="planning-identity"
					>
						<div className="border-b border-(--color-border-subtle) px-3 py-2.5">
							<h2 className="text-xs font-semibold uppercase tracking-[0.08em] text-(--color-foreground-secondary)">
								Planning identity
							</h2>
							<p className="mt-1 text-[11px] leading-4 text-(--color-foreground-tertiary)">
								启动后冻结；任何编辑都会使 Preflight 失效。
							</p>
						</div>
						<IdentityRow label="Experiment" value={draft.experimentId} />
						<IdentityRow label="Strategy" value={`${draft.strategyId}@${draft.strategyVersion}`} />
						<IdentityRow label="Snapshot" value={draft.snapshotId} />
						<nav aria-label="规划章节" className="border-b border-(--color-border-subtle) px-2 py-2">
							{PLANNING_SECTIONS.map((section, index) => (
								<div key={section} className="flex items-start gap-2 rounded-(--radius-sm) px-2 py-1.5 text-[11px]">
									<span className="font-data text-(--color-foreground-tertiary)">
										{String(index + 1).padStart(2, "0")}
									</span>
									<span className="leading-4 text-(--color-foreground-secondary)">{section}</span>
								</div>
							))}
						</nav>
						<div className="px-3 py-3">
							<p className="mb-2 text-xs uppercase tracking-[0.08em] text-(--color-foreground-tertiary)">
								Governance assistant
							</p>
							{currentIdentity ? (
								<AgentContextActions
									className="flex flex-col items-stretch gap-1.5"
									contextType="experiment-planning-draft"
									contextId={currentIdentity}
									evidenceObjective="复核当前实验 planning draft 的 frozen identity、预算与门禁"
									authorObjective="提出当前实验 planning draft 的结构化变更草案"
								/>
							) : (
								<p className="text-xs text-(--color-led-danger)">JSON 无效，Agent 上下文不可用。</p>
							)}
						</div>
					</aside>
				}
				main={
					<main
						className="h-full overflow-y-auto bg-(--color-surface-app) p-(--density-panel-padding)"
						data-info-level="l1"
						data-info-unit="planning-form"
					>
						<ExperimentConfigForm draft={draft} onChange={changeDraft} />
					</main>
				}
				inspector={
					<aside
						className="h-full overflow-y-auto border-l border-(--color-border-subtle) bg-(--color-surface-1)"
						data-info-level="l2"
						data-info-unit="experiment-preflight"
					>
						<ExperimentPreflightPanel
							preflight={preflight.data ?? null}
							isStale={stale}
							confirmed={confirmed}
							onConfirmedChange={setConfirmed}
						/>
					</aside>
				}
				logs={
					<section
						aria-label="实验规划日志"
						role="log"
						className="h-full min-h-[132px] overflow-y-auto border-t border-(--color-border-subtle) bg-(--color-surface-0) px-3 py-2"
						data-info-level="l2"
						data-info-unit="planning-log"
					>
						<div className="grid grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto] gap-x-5 gap-y-1 font-data text-[11px]">
							<p>
								<span className="text-(--color-foreground-tertiary)">PREFLIGHT</span> {preflightState}
							</p>
							<p className="truncate">
								<span className="text-(--color-foreground-tertiary)">PLAN HASH</span>{" "}
								{preflight.data?.planHash ?? "未生成"}
							</p>
							<p>
								<span className="text-(--color-foreground-tertiary)">CANDIDATES</span> {candidateCount ?? "invalid"}{" "}
								planned · limit 128
							</p>
							<p>
								<span className="text-(--color-foreground-tertiary)">LAUNCH</span>{" "}
								{launch.isPending ? "提交中" : canLaunch ? "已确认，可启动" : "等待确认"}
							</p>
							<p>
								<span className="text-(--color-foreground-tertiary)">WORKERS</span> {draft.workerCount}
							</p>
							<p>
								<span className="text-(--color-foreground-tertiary)">SEED</span> {draft.seed}
							</p>
						</div>
						{formError && (
							<p role="alert" className="mt-1 text-xs text-(--color-led-danger)">
								{formError}
							</p>
						)}
						{preflightError && (
							<p role="alert" className="mt-1 text-xs text-(--color-led-danger)">
								{preflightError}
							</p>
						)}
						{launchError && (
							<p role="alert" className="mt-1 text-xs text-(--color-led-danger)">
								{launchError}
								{launch.error instanceof ApiError && launch.error.status === 503
									? "。结果未知，重试复用同一 Idempotency-Key。"
									: ""}
							</p>
						)}
					</section>
				}
			/>
			<StatusBar />
		</section>
	);
}
