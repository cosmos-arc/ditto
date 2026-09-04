import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { StrategyDetail, StrategySpec } from "@/types/strategy";
import { mapStrategyDetail, serializeStrategySpec } from "../api/mappers";
import { strategyKeys } from "../api/query-keys";
import { createStrategy } from "../api/strategy-lifecycle";

export interface CreateStrategyVariables {
	readonly idempotencyKey: string;
	readonly name: string;
	readonly spec: StrategySpec;
	readonly strategyId: string;
	readonly tags: readonly string[];
}

/** Create one governed draft and refresh only strategy catalog queries. */
export function useCreateStrategy() {
	const queryClient = useQueryClient();
	return useMutation<StrategyDetail, Error, CreateStrategyVariables>({
		mutationFn: ({ idempotencyKey, name, spec, strategyId, tags }) =>
			createStrategy(
				{
					strategy_id: strategyId,
					name,
					spec_json: serializeStrategySpec({ ...spec, strategyId, name }),
					tags: [...tags],
				},
				idempotencyKey,
			).then(mapStrategyDetail),
		onSuccess: (detail) => {
			queryClient.setQueryData(strategyKeys.detail(detail.strategyId), detail);
			void queryClient.invalidateQueries({ queryKey: [...strategyKeys.all, "list"] });
		},
	});
}
