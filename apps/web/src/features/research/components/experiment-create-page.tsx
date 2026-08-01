import { useRef, useState } from "react";
import { Panel, PanelBody, PanelHeader, StatusBar } from "@/features/shell";
import { ApiError } from "@/lib/api-client";
import {
	buildExperimentPlanningRequest,
	createDefaultExperimentDraft,
	type ExperimentConfigDraft,
	type ExperimentPlanningRequest,
} from "../api/experiments";
import { useExperimentLaunch, useExperimentPreflight } from "../hooks";
import { ExperimentConfigForm } from "./experiment-config-form";
import { ExperimentPreflightPanel } from "./experiment-preflight-panel";

interface ExperimentCreatePageProps {
	readonly onLaunched?: (experimentId: string) => void;
}

function commandKey(): string {
	const randomId = globalThis.crypto?.randomUUID?.();
	return `experiment-launch-${randomId ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`}`;
}

function errorMessage(error: Error | null): string | null {
	if (!error) return null;
	if (error instanceof ApiError) return `${error.status} ${error.errorCode ?? "EXPERIMENT_ERROR"}: ${error.message}`;
	return error.message;
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
		currentIdentity = JSON.stringify(planning);
	} catch {
		planning = null;
	}
	const stale = preflight.data !== undefined && currentIdentity !== preflightIdentity;
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

	return (
		<>
			<main className="min-h-0 overflow-auto pb-(--height-status-bar)">
				<div className="mx-auto flex w-full max-w-[1600px] flex-col gap-(--section-gap) p-(--density-panel-padding)">
					<Panel>
						<PanelHeader title="创建研究实验" subtitle="固定完整 planning identity，经只读 preflight 后启动" />
						<PanelBody className="p-0">
							<ExperimentConfigForm draft={draft} onChange={changeDraft} />
						</PanelBody>
					</Panel>
					<ExperimentPreflightPanel
						preflight={preflight.data ?? null}
						isStale={stale}
						confirmed={confirmed}
						onConfirmedChange={setConfirmed}
					/>
					{formError && (
						<p role="alert" className="text-sm text-(--color-led-danger)">
							{formError}
						</p>
					)}
					{errorMessage(preflight.error) && (
						<p role="alert" className="text-sm text-(--color-led-danger)">
							{errorMessage(preflight.error)}
						</p>
					)}
					{errorMessage(launch.error) && (
						<p role="alert" className="text-sm text-(--color-led-danger)">
							{errorMessage(launch.error)}
							{launch.error instanceof ApiError && launch.error.status === 503
								? "。结果未知，重试复用同一 Idempotency-Key。"
								: ""}
						</p>
					)}
					<div className="sticky bottom-(--height-status-bar) flex flex-wrap justify-end gap-2 border-t border-(--color-border-subtle) bg-(--color-surface-1) py-3">
						<button
							type="button"
							onClick={runPreflight}
							disabled={preflight.isPending}
							className="rounded-(--radius-sm) border border-(--color-border-strong) px-3 py-2 text-sm disabled:opacity-50"
						>
							{preflight.isPending ? "Preflight 中…" : "运行只读 Preflight"}
						</button>
						<button
							type="button"
							onClick={runLaunch}
							disabled={!canLaunch || launch.isPending}
							className="rounded-(--radius-sm) bg-(--brand-accent) px-3 py-2 text-sm text-(--brand-accent-fg) disabled:opacity-50"
						>
							{launch.isPending ? "启动中…" : "启动实验"}
						</button>
					</div>
				</div>
			</main>
			<StatusBar />
		</>
	);
}
