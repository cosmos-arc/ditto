import { useMutation } from "@tanstack/react-query";
import type { StrategyAuthorPreview } from "@/types/strategy";
import { mapStrategyAuthorPreview } from "../api/mappers";
import { previewStrategyAuthor, type StrategyAuthorPreviewRequest } from "../api/strategy-lifecycle";

export type StrategyAuthorPreviewVariables = {
	readonly strategyId: string;
	readonly version: number;
	readonly payload: StrategyAuthorPreviewRequest;
};

/** Detached Author workbench: draft + compile + validate + diff + deterministic tests. */
export function useStrategyAuthorPreview() {
	return useMutation({
		mutationFn: ({ strategyId, version, payload }: StrategyAuthorPreviewVariables) =>
			previewStrategyAuthor(strategyId, version, payload).then(mapStrategyAuthorPreview),
	});
}

export type { StrategyAuthorPreview };
