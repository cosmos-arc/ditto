import { useQuery } from "@tanstack/react-query";
import { fetchBacktestRuns } from "../api/backtests";

/** 目录存在未落定 run 时继续读取真实任务状态；全部落定后停止轮询。 */
export function useBacktestRuns() {
	return useQuery({
		queryKey: ["backtests", "runs"],
		queryFn: fetchBacktestRuns,
		refetchInterval: (query) =>
			(query.state.data ?? []).some((run) => run.status === "pending" || run.status === "running") ? 2000 : false,
	});
}
