import { useState } from "react";
import { Button } from "@/components/ui/button";
import { CatalogLayout, Panel, PanelBody, PanelHeader } from "@/features/shell";
import {
	useDataProductCoverage,
	useDataProductEvidence,
	useDataProductLicense,
	useDataProductQuality,
	useDataProductRuns,
	useDataProducts,
} from "../hooks";
import { DataProductCatalog } from "./data-product-catalog";
import { DataProductCoverage } from "./data-product-coverage";
import { DataProductEvidence } from "./data-product-evidence";
import { DataProductOperations } from "./data-product-operations";
import { DataProductOverview as DataProductOverviewView } from "./data-product-overview";
import { DataProductQuality } from "./data-product-quality";
import { DataProductRuns } from "./data-product-runs";
import { DataProductToolbar, type WorkbenchView } from "./data-product-toolbar";

const PRODUCT_SKELETON_KEYS = ["one", "two", "three", "four", "five", "six", "seven", "eight"] as const;

function WorkbenchEmpty() {
	return (
		<Panel className="m-4 h-fit">
			<PanelHeader title="尚无 R2 数据产品" />
			<PanelBody className="p-4">
				<p className="max-w-[68ch] text-sm text-(--color-foreground-secondary)">
					先运行 acceptance fixture 建立 19 项 hard-scope contract，再刷新真实 API。页面不会使用 prototype fixture
					伪造就绪状态。
				</p>
			</PanelBody>
		</Panel>
	);
}

export function DataProductWorkbench() {
	const [selectedId, setSelectedId] = useState("");
	const [view, setView] = useState<WorkbenchView>("overview");
	const productsQuery = useDataProducts();
	const products = productsQuery.data ?? [];
	const activeProduct = products.find((product) => product.dataset_id === selectedId) ?? products[0];
	const activeId = activeProduct?.dataset_id ?? "";
	const coverageQuery = useDataProductCoverage(activeId);
	const qualityQuery = useDataProductQuality(activeId);
	const runsQuery = useDataProductRuns(activeId);
	const evidenceQuery = useDataProductEvidence(activeId);
	const licenseQuery = useDataProductLicense(activeId);

	function detailPanel() {
		if (!activeProduct) return <WorkbenchEmpty />;
		if (view === "coverage")
			return (
				<DataProductCoverage
					data={coverageQuery.data}
					isLoading={coverageQuery.isLoading}
					isError={coverageQuery.isError}
				/>
			);
		if (view === "quality")
			return (
				<DataProductQuality
					data={qualityQuery.data}
					isLoading={qualityQuery.isLoading}
					isError={qualityQuery.isError}
				/>
			);
		if (view === "runs")
			return (
				<DataProductRuns
					datasetId={activeId}
					data={runsQuery.data}
					isLoading={runsQuery.isLoading}
					isError={runsQuery.isError}
				/>
			);
		if (view === "evidence")
			return (
				<DataProductEvidence
					datasetId={activeId}
					evidence={evidenceQuery.data}
					license={licenseQuery.data}
					isLoading={evidenceQuery.isLoading || licenseQuery.isLoading}
					isError={evidenceQuery.isError || licenseQuery.isError}
				/>
			);
		if (view === "operations") return <DataProductOperations datasetId={activeId} />;
		return (
			<DataProductOverviewView
				product={activeProduct}
				certifiedCount={products.filter((product) => product.active_certification_report_id !== null).length}
				totalCount={products.length}
			/>
		);
	}

	const toolbar = (
		<DataProductToolbar view={view} onViewChange={setView} onRefresh={() => void productsQuery.refetch()} />
	);

	if (productsQuery.isLoading)
		return (
			<div data-domain="platform" className="h-full">
				<CatalogLayout
					toolbar={toolbar}
					main={
						<Panel className="m-4">
							<PanelHeader title="正在加载产品目录" />
							<PanelBody className="space-y-2 p-3">
								{PRODUCT_SKELETON_KEYS.map((key) => (
									<div key={key} className="h-8 animate-pulse rounded-(--radius-sm) bg-(--color-surface-muted)" />
								))}
							</PanelBody>
						</Panel>
					}
					detail={
						<Panel className="m-4 ml-0">
							<PanelHeader title="正在加载证据" />
							<PanelBody className="p-3">
								<div className="h-28 animate-pulse rounded-(--radius-sm) bg-(--color-surface-muted)" />
							</PanelBody>
						</Panel>
					}
				/>
			</div>
		);
	if (productsQuery.isError)
		return (
			<div data-domain="platform" className="h-full">
				<CatalogLayout
					toolbar={toolbar}
					main={
						<Panel className="m-4">
							<PanelHeader title="数据产品 API 不可用" />
							<PanelBody className="p-4">
								<p role="alert" className="text-sm text-(--color-risk-critical-fg)">
									{productsQuery.error.message}
								</p>
								<Button
									className="mt-3"
									type="button"
									variant="outline"
									size="sm"
									onClick={() => void productsQuery.refetch()}
								>
									重试
								</Button>
							</PanelBody>
						</Panel>
					}
				/>
			</div>
		);
	if (products.length === 0)
		return (
			<div data-domain="platform" className="h-full">
				<CatalogLayout toolbar={toolbar} main={<WorkbenchEmpty />} />
			</div>
		);

	return (
		<div data-domain="platform" className="h-full">
			<CatalogLayout
				className="pb-(--height-status-bar) max-lg:grid-cols-1 max-lg:grid-rows-[auto_minmax(16rem,1fr)_minmax(18rem,1.2fr)] max-lg:[grid-template-areas:'toolbar'_'main'_'detail']"
				toolbar={toolbar}
				main={
					<section aria-label="数据产品目录" className="h-full p-(--density-panel-padding)">
						<DataProductCatalog products={products} selectedId={activeId} onSelect={setSelectedId} />
					</section>
				}
				detail={
					<section
						id="data-products-tabpanel"
						role="tabpanel"
						aria-labelledby={`data-products-tab-${view}`}
						className="h-full p-(--density-panel-padding) lg:pl-0"
					>
						{detailPanel()}
					</section>
				}
			/>
		</div>
	);
}
