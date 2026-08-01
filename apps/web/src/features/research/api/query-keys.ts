/**
 * Review query-key factory（research 域）。
 *
 * 参照 `features/strategy/api/query-keys.ts` 的 factory 范式：`all` 根元组用于
 * scope 失效（治理决策后 `[...reviewKeys.all]` 一并失效 list + 全部 packet 缓存）。
 */
export const reviewKeys = {
	all: ["research", "reviews"] as const,
	list: () => [...reviewKeys.all, "list"] as const,
	packet: (experimentId: string) => [...reviewKeys.all, "packet", experimentId] as const,
} as const;

export const experimentKeys = {
	all: ["research", "experiments"] as const,
	list: () => [...experimentKeys.all, "list"] as const,
	detail: (experimentId: string) => [...experimentKeys.all, "detail", experimentId] as const,
} as const;
