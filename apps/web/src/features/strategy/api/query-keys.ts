/**
 * Strategy feature TanStack Query key factory。
 *
 * 范式与 trading 一致：`all` 为命名空间根，用于 scope 失效；每个 key 是工厂函数，
 * 可选参数回退稳定字面量，保证未参数化查询共享 key。
 */
export const strategyKeys = {
	all: ["strategy"] as const,
	list: (limit?: number, offset?: number) => [...strategyKeys.all, "list", limit ?? 50, offset ?? 0] as const,
	detail: (strategyId: string) => [...strategyKeys.all, "detail", strategyId] as const,
	versions: (strategyId: string) => [...strategyKeys.all, "versions", strategyId] as const,
	active: (strategyId: string) => [...strategyKeys.all, "active", strategyId] as const,
	diff: (strategyId: string, version: number) => [...strategyKeys.all, "diff", strategyId, version] as const,
	nodeDescriptors: () => [...strategyKeys.all, "node-descriptors"] as const,
} as const;
