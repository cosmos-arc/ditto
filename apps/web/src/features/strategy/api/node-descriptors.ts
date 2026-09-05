import { apiClient } from "@/api";
import type { components } from "@/api/generated/schema";

/** 流水线节点描述符（只读调色板数据源）DTO。 */
export type NodeDescriptorResponse = components["schemas"]["NodeDescriptorResponse"];

/** 列出所有受治理的流水线节点描述符。 */
export function fetchNodeDescriptors(): Promise<NodeDescriptorResponse[]> {
	return apiClient.get("/api/v1/research/node-descriptors");
}
