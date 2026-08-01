import { ContextSection } from "@/components/domain/context-section";
import type { ExperimentConfigDraft } from "../api/experiments";
import { estimateCandidateCount } from "../api/experiments";

interface ExperimentConfigFormProps {
	readonly draft: ExperimentConfigDraft;
	readonly onChange: (draft: ExperimentConfigDraft) => void;
}

const INPUT_CLASS =
	"w-full rounded-(--radius-sm) border border-(--color-border-subtle) bg-(--color-surface-1) px-2 py-1.5 font-data text-xs text-(--color-foreground)";

function Field({
	label,
	value,
	onChange,
	type = "text",
}: {
	readonly label: string;
	readonly value: string | number;
	readonly onChange: (value: string) => void;
	readonly type?: "text" | "number";
}) {
	return (
		<label className="flex min-w-0 flex-col gap-1 text-xs text-(--color-foreground-secondary)">
			<span>{label}</span>
			<input
				className={INPUT_CLASS}
				aria-label={label}
				type={type}
				value={value}
				onChange={(e) => onChange(e.target.value)}
			/>
		</label>
	);
}

function JsonField({
	label,
	value,
	onChange,
}: {
	readonly label: string;
	readonly value: string;
	readonly onChange: (value: string) => void;
}) {
	return (
		<label className="flex min-w-0 flex-col gap-1 text-xs text-(--color-foreground-secondary)">
			<span>{label}</span>
			<textarea
				className={`${INPUT_CLASS} min-h-28 resize-y`}
				aria-label={label}
				spellCheck={false}
				value={value}
				onChange={(e) => onChange(e.target.value)}
			/>
		</label>
	);
}

export function ExperimentConfigForm({ draft, onChange }: ExperimentConfigFormProps) {
	const update = <K extends keyof ExperimentConfigDraft>(key: K, value: ExperimentConfigDraft[K]): void => {
		onChange({ ...draft, [key]: value });
	};
	const candidateCount = estimateCandidateCount(draft.axesJson);

	return (
		<div className="flex flex-col gap-(--section-gap)">
			<ContextSection title="Experiment identity">
				<div className="grid gap-3 p-(--density-panel-padding) sm:grid-cols-2 xl:grid-cols-3">
					<Field label="Experiment ID" value={draft.experimentId} onChange={(v) => update("experimentId", v)} />
					<Field
						label="Research cycle ID"
						value={draft.researchCycleId}
						onChange={(v) => update("researchCycleId", v)}
					/>
					<Field
						label="Research cycle hash"
						value={draft.researchCycleHash}
						onChange={(v) => update("researchCycleHash", v)}
					/>
				</div>
			</ContextSection>

			<ContextSection title="Frozen strategy and snapshot">
				<div className="grid gap-3 p-(--density-panel-padding) sm:grid-cols-2 xl:grid-cols-3">
					<Field label="Strategy ID" value={draft.strategyId} onChange={(v) => update("strategyId", v)} />
					<Field
						label="Strategy version"
						type="number"
						value={draft.strategyVersion}
						onChange={(v) => update("strategyVersion", Number(v))}
					/>
					<Field
						label="Strategy spec hash"
						value={draft.strategySpecHash}
						onChange={(v) => update("strategySpecHash", v)}
					/>
					<Field label="Snapshot ID" value={draft.snapshotId} onChange={(v) => update("snapshotId", v)} />
					<Field
						label="Snapshot manifest hash"
						value={draft.snapshotManifestHash}
						onChange={(v) => update("snapshotManifestHash", v)}
					/>
					<div className="sm:col-span-2 xl:col-span-3">
						<JsonField
							label="Frozen StrategySpec JSON"
							value={draft.strategySpecJson}
							onChange={(v) => update("strategySpecJson", v)}
						/>
					</div>
				</div>
			</ContextSection>

			<ContextSection title="Validation and promotion">
				<div className="grid gap-3 p-(--density-panel-padding) xl:grid-cols-2">
					<JsonField
						label="Canonical validation JSON"
						value={draft.validationJson}
						onChange={(v) => update("validationJson", v)}
					/>
					<JsonField
						label="Promotion objective JSON"
						value={draft.promotionObjectiveJson}
						onChange={(v) => update("promotionObjectiveJson", v)}
					/>
				</div>
			</ContextSection>

			<ContextSection title="Candidate matrix">
				<div className="grid gap-3 p-(--density-panel-padding) sm:grid-cols-2 xl:grid-cols-3">
					<Field
						label="Baseline descriptor"
						value={draft.baselineDescriptorType}
						onChange={(v) => update("baselineDescriptorType", v)}
					/>
					<Field
						label="Baseline schema version"
						type="number"
						value={draft.baselineSchemaVersion}
						onChange={(v) => update("baselineSchemaVersion", Number(v))}
					/>
					<Field
						label="Candidate limit"
						type="number"
						value={draft.candidateLimit}
						onChange={(v) => update("candidateLimit", Number(v))}
					/>
					<div className="sm:col-span-2 xl:col-span-3 grid gap-3 xl:grid-cols-2">
						<JsonField
							label="Baseline payload JSON"
							value={draft.baselinePayloadJson}
							onChange={(v) => update("baselinePayloadJson", v)}
						/>
						<JsonField label="Matrix axes JSON" value={draft.axesJson} onChange={(v) => update("axesJson", v)} />
					</div>
					<div className="rounded-(--radius-sm) border border-(--color-border-subtle) p-3">
						<span className="block text-xs text-(--color-foreground-tertiary)">Candidate estimate / hard ceiling</span>
						<strong className="font-data text-lg">
							{candidateCount === null ? "invalid" : `${candidateCount} / 128`}
						</strong>
					</div>
				</div>
			</ContextSection>

			<ContextSection title="Data, cost and execution policy">
				<div className="grid gap-3 p-(--density-panel-padding) sm:grid-cols-2 xl:grid-cols-4">
					<div className="sm:col-span-2 xl:col-span-4">
						<JsonField
							label="Dataset requirements JSON"
							value={draft.datasetRequirementsJson}
							onChange={(v) => update("datasetRequirementsJson", v)}
						/>
					</div>
					<Field
						label="Bytes per run"
						type="number"
						value={draft.bytesPerRun}
						onChange={(v) => update("bytesPerRun", Number(v))}
					/>
					<Field
						label="Bytes per trading session"
						type="number"
						value={draft.bytesPerTradingSession}
						onChange={(v) => update("bytesPerTradingSession", Number(v))}
					/>
					<Field
						label="Fold run limit"
						type="number"
						value={draft.foldRunLimit}
						onChange={(v) => update("foldRunLimit", Number(v))}
					/>
					<Field
						label="Trading session limit"
						type="number"
						value={draft.tradingSessionLimit}
						onChange={(v) => update("tradingSessionLimit", Number(v))}
					/>
					<Field
						label="Disk byte limit"
						type="number"
						value={draft.diskByteLimit}
						onChange={(v) => update("diskByteLimit", Number(v))}
					/>
					<Field label="Seed" type="number" value={draft.seed} onChange={(v) => update("seed", Number(v))} />
					<label className="flex flex-col gap-1 text-xs text-(--color-foreground-secondary)">
						<span>Worker count</span>
						<select
							className={INPUT_CLASS}
							aria-label="Worker count"
							value={draft.workerCount}
							onChange={(e) => update("workerCount", Number(e.target.value) as 2 | 4)}
						>
							<option value={2}>2</option>
							<option value={4}>4</option>
						</select>
					</label>
					<label className="flex flex-col gap-1 text-xs text-(--color-foreground-secondary)">
						<span>Failure policy</span>
						<select
							className={INPUT_CLASS}
							aria-label="Failure policy"
							value={draft.failurePolicy}
							onChange={(e) => update("failurePolicy", e.target.value as ExperimentConfigDraft["failurePolicy"])}
						>
							<option value="continue_candidate_failures">Continue candidate failures</option>
							<option value="fail_fast">Fail fast</option>
						</select>
					</label>
				</div>
			</ContextSection>
		</div>
	);
}
