import { StatusBadge } from "@/components/status";
import type { AgentApprovalView } from "../types";

type Change = {
	readonly operation: string;
	readonly path: string;
	readonly before: unknown;
	readonly after: unknown;
};

function record(value: unknown): Readonly<Record<string, unknown>> | null {
	return typeof value === "object" && value !== null && !Array.isArray(value)
		? (value as Readonly<Record<string, unknown>>)
		: null;
}

function changeRows(payload: Readonly<Record<string, unknown>>): readonly Change[] {
	const raw = Array.isArray(payload.changes) ? payload.changes : Array.isArray(payload.patch) ? payload.patch : [];
	return raw.flatMap((value) => {
		const item = record(value);
		if (!item || typeof item.path !== "string") return [];
		return [
			{
				operation:
					typeof item.op === "string" ? item.op : typeof item.operation === "string" ? item.operation : "change",
				path: item.path,
				before: item.before ?? null,
				after: item.after ?? item.value ?? null,
			},
		];
	});
}

function exactText(value: unknown): string {
	if (typeof value === "string") return value;
	const encoded = JSON.stringify(value);
	return encoded ?? "not provided";
}

function stringArray(value: unknown): readonly string[] {
	return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

export function AgentAuthorPreview({ approval }: { readonly approval: AgentApprovalView }) {
	const payload = approval.actionPayload;
	const exactPayload = { ...payload, ...(record(payload.parameters) ?? {}) };
	const changes = changeRows(exactPayload);
	const evidenceRefs = stringArray(exactPayload.evidence_refs);
	const artifactHash =
		typeof exactPayload.artifact_hash === "string"
			? exactPayload.artifact_hash
			: typeof exactPayload.manifest_hash === "string"
				? exactPayload.manifest_hash
				: null;

	return (
		<section
			aria-label="Author structured preview"
			className="rounded-(--radius-sm) border border-(--color-border-subtle) p-4"
		>
			<div className="flex flex-wrap items-center justify-between gap-2">
				<div>
					<h2 className="text-sm font-semibold">Author structured preview</h2>
					<p className="mt-1 font-data text-xs text-(--color-foreground-tertiary)">
						{approval.actionType} · {approval.targetIdentity}
					</p>
				</div>
				<StatusBadge label="PREVIEW ONLY · NOT APPLIED" variant="warning" />
			</div>

			{changes.length > 0 ? (
				<div className="mt-4 overflow-x-auto">
					<table className="w-full min-w-160 text-left text-xs">
						<thead className="bg-(--color-surface-strip) text-(--color-foreground-tertiary)">
							<tr>
								<th className="px-3 py-2 font-medium">operation</th>
								<th className="px-3 py-2 font-medium">field</th>
								<th className="px-3 py-2 font-medium">before</th>
								<th className="px-3 py-2 font-medium">after</th>
							</tr>
						</thead>
						<tbody className="divide-y divide-(--color-border-subtle)">
							{changes.map((change) => (
								<tr key={`${change.path}:${change.operation}:${exactText(change.before)}:${exactText(change.after)}`}>
									<td className="px-3 py-2 font-data">{change.operation}</td>
									<td className="px-3 py-2 font-data">{change.path}</td>
									<td className="px-3 py-2 font-data text-(--color-foreground-tertiary)">{exactText(change.before)}</td>
									<td className="px-3 py-2 font-data text-(--color-foreground)">{exactText(change.after)}</td>
								</tr>
							))}
						</tbody>
					</table>
				</div>
			) : (
				<p className="mt-4 text-xs text-(--color-foreground-tertiary)">
					当前 exact payload 未提供可识别的字段级 changes/patch；不从自然语言推断变更。
				</p>
			)}

			<div className="mt-4 grid gap-3 sm:grid-cols-2">
				<div className="rounded-(--radius-sm) bg-(--color-surface-strip) p-3">
					<p className="text-xs text-(--color-foreground-tertiary)">validation / guardrail</p>
					<p className="mt-1 break-all font-data text-xs">{exactText(exactPayload.validation ?? "not provided")}</p>
					<p className="mt-1 break-all font-data text-xs">{exactText(exactPayload.guardrail ?? "not provided")}</p>
				</div>
				<div className="rounded-(--radius-sm) bg-(--color-surface-strip) p-3">
					<p className="text-xs text-(--color-foreground-tertiary)">artifact / evidence</p>
					<p className="mt-1 break-all font-data text-xs">{artifactHash ?? "not provided"}</p>
					{evidenceRefs.length > 0 ? (
						<ul className="mt-1 space-y-1">
							{evidenceRefs.map((ref) => (
								<li key={ref} className="break-all font-data text-xs text-(--color-accent)">
									{ref}
								</li>
							))}
						</ul>
					) : (
						<p className="mt-1 text-xs text-(--color-risk-warning-fg)">evidence refs not provided</p>
					)}
				</div>
			</div>

			<p className="mt-4 text-xs text-(--color-foreground-secondary)">
				审批后必须从{" "}
				<a
					className="font-data text-(--color-accent) hover:underline"
					href={`/research/agent?tab=runs&selected=${encodeURIComponent(approval.runId)}`}
				>
					Run {approval.runId}
				</a>{" "}
				重新读取后端实际 artifact/result identity；此预览不乐观标记为已应用。
			</p>
		</section>
	);
}
