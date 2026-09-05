import { apiClient } from "@/api";
import type { components } from "@/api/generated/schema";

export const DEFAULT_DATA_PRODUCT_PROFILE = "research_daily";

export type DataProductView = components["schemas"]["DataProductViewResponse"];
export type DataProductCoverage = components["schemas"]["DataProductCoverageResponse"];
export type DataProductCheck = components["schemas"]["DataProductCheckResponse"];
export type DataProductQuality = components["schemas"]["DataProductQualityResponse"];
export type DataProductRun = components["schemas"]["DataProductRunResponse"];
export type DataProductEvidence = components["schemas"]["DataProductEvidenceResponse"];
export type DataProductLicense = components["schemas"]["DataProductLicenseResponse"];

export const dataProductKeys = {
	all: ["data-products"] as const,
	list: (profile: string) => [...dataProductKeys.all, "list", profile] as const,
	detail: (datasetId: string, profile: string) => [...dataProductKeys.all, datasetId, profile] as const,
	coverage: (datasetId: string, profile: string) =>
		[...dataProductKeys.detail(datasetId, profile), "coverage"] as const,
	quality: (datasetId: string, profile: string) => [...dataProductKeys.detail(datasetId, profile), "quality"] as const,
	runs: (datasetId: string, profile: string) => [...dataProductKeys.detail(datasetId, profile), "runs"] as const,
	evidence: (datasetId: string, profile: string) =>
		[...dataProductKeys.detail(datasetId, profile), "evidence"] as const,
	license: (datasetId: string, profile: string) => [...dataProductKeys.detail(datasetId, profile), "license"] as const,
};

export function fetchDataProducts(profile = DEFAULT_DATA_PRODUCT_PROFILE): Promise<readonly DataProductView[]> {
	return apiClient.get("/api/v1/data-products", { params: { query: { profile } } });
}

export function fetchDataProductCoverage(
	datasetId: string,
	profile = DEFAULT_DATA_PRODUCT_PROFILE,
): Promise<DataProductCoverage> {
	return apiClient.get("/api/v1/data-products/{dataset_id}/coverage", {
		params: { path: { dataset_id: datasetId }, query: { profile } },
	});
}

export function fetchDataProductQuality(
	datasetId: string,
	profile = DEFAULT_DATA_PRODUCT_PROFILE,
): Promise<DataProductQuality> {
	return apiClient.get("/api/v1/data-products/{dataset_id}/quality", {
		params: { path: { dataset_id: datasetId }, query: { profile } },
	});
}

export function fetchDataProductRuns(
	datasetId: string,
	profile = DEFAULT_DATA_PRODUCT_PROFILE,
): Promise<readonly DataProductRun[]> {
	return apiClient.get("/api/v1/data-products/{dataset_id}/runs", {
		params: { path: { dataset_id: datasetId }, query: { profile } },
	});
}

export function fetchDataProductEvidence(
	datasetId: string,
	profile = DEFAULT_DATA_PRODUCT_PROFILE,
): Promise<DataProductEvidence> {
	return apiClient.get("/api/v1/data-products/{dataset_id}/evidence", {
		params: { path: { dataset_id: datasetId }, query: { profile } },
	});
}

export function fetchDataProductLicense(
	datasetId: string,
	profile = DEFAULT_DATA_PRODUCT_PROFILE,
): Promise<DataProductLicense> {
	return apiClient.get("/api/v1/data-products/{dataset_id}/license", {
		params: { path: { dataset_id: datasetId }, query: { profile } },
	});
}
