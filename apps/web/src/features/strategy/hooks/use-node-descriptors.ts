import { useQuery } from "@tanstack/react-query";
import type { NodeDescriptorView } from "@/types/strategy";
import { mapNodeDescriptor } from "../api/mappers";
import { fetchNodeDescriptors } from "../api/node-descriptors";
import { strategyKeys } from "../api/query-keys";

/** 列出受治理的流水线节点描述符（node-library 调色板数据源）。 */
export function useNodeDescriptors() {
	return useQuery({
		queryKey: strategyKeys.nodeDescriptors(),
		queryFn: async () => (await fetchNodeDescriptors()).map(mapNodeDescriptor),
	});
}

export type { NodeDescriptorView };
