import { Panel, PanelBody, PanelHeader } from "@/features/shell";
import type { DataProductLicense, DataProductEvidence as EvidenceModel } from "../api";
import { OperationPreview } from "./operation-preview";

interface DataProductEvidenceProps {
	readonly datasetId: string;
	readonly evidence?: EvidenceModel | undefined;
	readonly license?: DataProductLicense | undefined;
	readonly isLoading: boolean;
	readonly isError: boolean;
}

function EvidenceList({ title, values }: { readonly title: string; readonly values: readonly string[] }) {
	return (
		<section aria-label={title}>
			<h3 className="text-xs font-medium text-(--color-foreground-tertiary)">{title}</h3>
			<ul className="mt-2 space-y-1">
				{values.length === 0 ? (
					<li className="text-xs text-(--color-foreground-tertiary)">none</li>
				) : (
					values.map((value) => (
						<li
							key={value}
							className="break-all rounded-(--radius-sm) bg-(--color-surface-muted) px-2 py-1 font-code text-xs text-(--color-foreground-secondary)"
						>
							{value}
						</li>
					))
				)}
			</ul>
		</section>
	);
}

export function DataProductEvidence({ datasetId, evidence, license, isLoading, isError }: DataProductEvidenceProps) {
	return (
		<Panel className="h-full" data-info-level="l1" data-info-unit="data-product-evidence">
			<PanelHeader title="Evidence & License" subtitle={evidence?.report_id} />
			<PanelBody className="p-(--density-panel-padding)">
				{isLoading && (
					<div
						role="status"
						aria-label="正在加载证据与许可"
						className="h-24 animate-pulse rounded-(--radius-sm) bg-(--color-surface-muted)"
					/>
				)}
				{isError && (
					<p role="alert" className="text-sm text-(--color-risk-critical-fg)">
						认证或许可证据不可解析，promotion 保持阻塞。
					</p>
				)}
				{evidence && license && (
					<>
						<div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
							<EvidenceList title="Provider source" values={evidence.source_ids} />
							<EvidenceList title="Schema version" values={evidence.schema_versions} />
							<EvidenceList title="Source snapshot" values={evidence.snapshot_ids} />
							<EvidenceList title="Fallback history" values={evidence.fallback_history} />
							<EvidenceList title="Override history" values={evidence.override_history} />
							<EvidenceList title="Reviewed license" values={license.license_record_ids} />
						</div>
						<section aria-label="认证内容哈希" className="mt-5 border-t border-(--color-border-subtle) pt-4">
							<p className="text-xs text-(--color-foreground-tertiary)">Immutable content hash</p>
							<code className="mt-1 block break-all font-code text-xs text-(--color-foreground)">
								{evidence.content_hash}
							</code>
						</section>
					</>
				)}
				<section aria-label="认证治理操作" className="mt-5 border-t border-(--color-border-subtle) pt-4">
					<h3 className="text-sm font-medium text-(--color-foreground)">认证治理</h3>
					<p className="mt-1 text-xs text-(--color-foreground-secondary)">
						Certification、promotion 与 revoke 只追加证据，不覆盖历史。
					</p>
					<div className="mt-3">
						<OperationPreview datasetId={datasetId} operations={["certify", "promotion", "revoke"]} />
					</div>
				</section>
			</PanelBody>
		</Panel>
	);
}
