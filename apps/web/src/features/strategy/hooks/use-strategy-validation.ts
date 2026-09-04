import { useMutation } from "@tanstack/react-query";
import type { SpecValidation } from "@/types/strategy";
import { mapSpecValidation } from "../api/mappers";
import { validateSpec } from "../api/strategy-lifecycle";

export type ValidateSpecVariables = {
	readonly strategyId: string;
	readonly version: number;
	readonly specJson: Readonly<Record<string, unknown>>;
};

/** Pre-save candidate spec 校验（canonical hash + validity + change-detection）。 */
export function useStrategyValidation() {
	return useMutation({
		mutationFn: ({ strategyId, version, specJson }: ValidateSpecVariables) =>
			validateSpec(strategyId, version, specJson).then(mapSpecValidation),
	});
}

export type { SpecValidation };
