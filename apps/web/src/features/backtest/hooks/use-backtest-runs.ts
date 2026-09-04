import { useQuery } from "@tanstack/react-query";
import { fetchBacktestRuns } from "../api/backtests";

export function useBacktestRuns() {
	return useQuery({
		queryKey: ["backtests", "runs"],
		queryFn: fetchBacktestRuns,
	});
}
