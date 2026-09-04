import { Panel, PanelBody, PanelHeader } from "@/features/shell";
import type { DataProductView } from "../api";

interface DataProductCatalogProps {
	readonly products: readonly DataProductView[];
	readonly selectedId: string;
	readonly onSelect: (datasetId: string) => void;
}

export function DataProductCatalog({ products, selectedId, onSelect }: DataProductCatalogProps) {
	return (
		<Panel className="h-full" data-info-level="l1" data-info-unit="data-product-catalog">
			<PanelHeader title="R2 Hard Scope" count={products.length} />
			<PanelBody>
				<div className="overflow-x-auto">
					<table aria-label="R2 数据产品目录" className="w-full min-w-[40rem] text-left text-xs">
						<thead className="sticky top-0 z-10 bg-(--color-surface-strip) text-(--color-foreground-tertiary)">
							<tr>
								<th className="px-3 py-2 font-medium">Dataset</th>
								<th className="px-3 py-2 font-medium">Maturity</th>
								<th className="px-3 py-2 font-medium">Frequency</th>
								<th className="px-3 py-2 font-medium">Certification</th>
							</tr>
						</thead>
						<tbody className="divide-y divide-(--color-border-subtle)">
							{products.map((product) => {
								const certified = product.active_certification_report_id !== null;
								return (
									<tr
										key={product.dataset_id}
										className={selectedId === product.dataset_id ? "bg-(--color-interaction-selected-bg)" : undefined}
									>
										<td className="px-3 py-1.5">
											<button
												type="button"
												aria-pressed={selectedId === product.dataset_id}
												onClick={() => onSelect(product.dataset_id)}
												className="w-full rounded-(--radius-sm) text-left font-code text-xs text-(--color-foreground) outline-none focus-visible:ring-3 focus-visible:ring-(--color-focus-ring)"
											>
												{product.dataset_id}
												<span className="sr-only"> {certified ? "已认证" : "待认证"}</span>
											</button>
										</td>
										<td className="px-3 py-1.5 font-data text-(--color-foreground-secondary)">{product.maturity}</td>
										<td className="px-3 py-1.5 font-data text-(--color-foreground-tertiary)">{product.frequency}</td>
										<td
											className={
												certified
													? "px-3 py-1.5 font-medium text-(--color-system-healthy-fg)"
													: "px-3 py-1.5 font-medium text-(--color-system-degraded-fg)"
											}
										>
											{certified ? "✓ 已认证" : "○ 待认证"}
										</td>
									</tr>
								);
							})}
						</tbody>
					</table>
				</div>
			</PanelBody>
		</Panel>
	);
}
