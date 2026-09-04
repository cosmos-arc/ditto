import { useQuery } from "@tanstack/react-query";
import {
	DEFAULT_DATA_PRODUCT_PROFILE,
	dataProductKeys,
	fetchDataProductCoverage,
	fetchDataProductEvidence,
	fetchDataProductLicense,
	fetchDataProductQuality,
	fetchDataProductRuns,
	fetchDataProducts,
} from "../api";

export function useDataProducts(profile = DEFAULT_DATA_PRODUCT_PROFILE) {
	return useQuery({
		queryKey: dataProductKeys.list(profile),
		queryFn: () => fetchDataProducts(profile),
	});
}

export function useDataProductCoverage(datasetId: string, profile = DEFAULT_DATA_PRODUCT_PROFILE, enabled = true) {
	return useQuery({
		queryKey: dataProductKeys.coverage(datasetId, profile),
		queryFn: () => fetchDataProductCoverage(datasetId, profile),
		enabled: enabled && datasetId.length > 0,
	});
}

export function useDataProductQuality(datasetId: string, profile = DEFAULT_DATA_PRODUCT_PROFILE, enabled = true) {
	return useQuery({
		queryKey: dataProductKeys.quality(datasetId, profile),
		queryFn: () => fetchDataProductQuality(datasetId, profile),
		enabled: enabled && datasetId.length > 0,
	});
}

export function useDataProductRuns(datasetId: string, profile = DEFAULT_DATA_PRODUCT_PROFILE, enabled = true) {
	return useQuery({
		queryKey: dataProductKeys.runs(datasetId, profile),
		queryFn: () => fetchDataProductRuns(datasetId, profile),
		enabled: enabled && datasetId.length > 0,
	});
}

export function useDataProductEvidence(datasetId: string, profile = DEFAULT_DATA_PRODUCT_PROFILE, enabled = true) {
	return useQuery({
		queryKey: dataProductKeys.evidence(datasetId, profile),
		queryFn: () => fetchDataProductEvidence(datasetId, profile),
		enabled: enabled && datasetId.length > 0,
	});
}

export function useDataProductLicense(datasetId: string, profile = DEFAULT_DATA_PRODUCT_PROFILE, enabled = true) {
	return useQuery({
		queryKey: dataProductKeys.license(datasetId, profile),
		queryFn: () => fetchDataProductLicense(datasetId, profile),
		enabled: enabled && datasetId.length > 0,
	});
}
