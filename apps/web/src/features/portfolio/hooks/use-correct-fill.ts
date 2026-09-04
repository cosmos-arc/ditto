import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
	type FillAdjustmentResponse,
	type ReplaceFillRequest,
	replaceFill,
	type VoidFillRequest,
	voidFill,
} from "../api/fills";
import { tradingKeys } from "../api/query-keys";

const CORRECTION_INVALIDATION_SCOPES = ["daily-decision", "positions", "deviation", "pnl", "fills"] as const;

export type CorrectFillCommand =
	| { readonly kind: "void"; readonly fillId: string; readonly payload: VoidFillRequest }
	| { readonly kind: "replace"; readonly fillId: string; readonly payload: ReplaceFillRequest };

function correctFill(command: CorrectFillCommand): Promise<FillAdjustmentResponse> {
	return command.kind === "void"
		? voidFill(command.fillId, command.payload)
		: replaceFill(command.fillId, command.payload);
}

export function useCorrectFill() {
	const queryClient = useQueryClient();

	return useMutation({
		mutationFn: correctFill,
		onSuccess: () => {
			for (const scope of CORRECTION_INVALIDATION_SCOPES) {
				void queryClient.invalidateQueries({ queryKey: [...tradingKeys.all, scope] });
			}
		},
	});
}
