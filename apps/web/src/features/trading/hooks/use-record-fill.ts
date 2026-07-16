import { useMutation, useQueryClient } from "@tanstack/react-query";
import { recordFill, type RecordFillRequest } from "../api/fills";
import { tradingKeys } from "../api/query-keys";

const RECORD_FILL_INVALIDATION_SCOPES = [
	"daily-decision",
	"positions",
	"deviation",
	"pnl",
	"fills",
] as const;

export function useRecordFill() {
	const queryClient = useQueryClient();

	return useMutation({
		mutationFn: (payload: RecordFillRequest) => recordFill(payload),
		onSuccess: () => {
			for (const scope of RECORD_FILL_INVALIDATION_SCOPES) {
				void queryClient.invalidateQueries({ queryKey: [...tradingKeys.all, scope] });
			}
		},
	});
}
