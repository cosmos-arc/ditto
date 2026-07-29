import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { StrategyDetail, StrategySpec } from "@/types/strategy";
import { mapStrategyDetail, serializeStrategySpec } from "../api/mappers";
import { strategyKeys } from "../api/query-keys";
import { updateStrategy } from "../api/strategy-lifecycle";
import { useStrategyStudioStore } from "../state/strategy-studio-store";

export type SaveStrategyVariables = {
	readonly strategyId: string;
	readonly version: number;
	readonly spec: StrategySpec;
	readonly name: string;
	readonly tags: readonly string[];
};

/** 保存后失效的 query scope（版本列表、详情、列表都会因新 draft version 而变化）。 */
const SAVE_INVALIDATION_SCOPES = ["versions", "detail", "list"] as const;

/**
 * 保存编辑（`PUT /v1/strategies/{id}`，version 乐观锁 → 后端 governance create_draft(parent)
 * 产生新 version）。成功后把返回 spec 重新载入 store（同步 working/saved，清除 dirty）并失效
 * versions/detail/list scope。
 */
export function useStrategySave() {
	const queryClient = useQueryClient();
	const loadSpec = useStrategyStudioStore((s) => s.loadSpec);

	return useMutation<StrategyDetail, Error, SaveStrategyVariables>({
		mutationFn: ({ strategyId, version, spec, name, tags }) =>
			updateStrategy(strategyId, {
				name,
				spec_json: serializeStrategySpec(spec),
				tags: [...tags],
				version,
			}).then(mapStrategyDetail),
		onSuccess: (detail) => {
			loadSpec(detail.spec);
			for (const scope of SAVE_INVALIDATION_SCOPES) {
				void queryClient.invalidateQueries({ queryKey: [...strategyKeys.all, scope] });
			}
		},
	});
}
