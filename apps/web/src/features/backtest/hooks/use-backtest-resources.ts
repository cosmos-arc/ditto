import { useQuery } from "@tanstack/react-query";
import {
	fetchBacktestAudit,
	fetchBacktestBenchmark,
	fetchBacktestNav,
	fetchBacktestReport,
	fetchBacktestRun,
	fetchBacktestTrades,
} from "../api/backtests";

export const backtestKeys = {
	all: ["backtests"] as const,
	run: (runId: string) => [...backtestKeys.all, "run", runId] as const,
	report: (runId: string) => [...backtestKeys.run(runId), "report"] as const,
	nav: (runId: string) => [...backtestKeys.run(runId), "nav"] as const,
	benchmark: (runId: string) => [...backtestKeys.run(runId), "benchmark"] as const,
	trades: (runId: string) => [...backtestKeys.run(runId), "trades"] as const,
	audit: (runId: string) => [...backtestKeys.run(runId), "audit"] as const,
};

export function useBacktestRun(runId: string) {
	return useQuery({
		queryKey: backtestKeys.run(runId),
		queryFn: () => fetchBacktestRun(runId),
		enabled: runId.length > 0,
	});
}

export function useBacktestReport(runId: string) {
	return useQuery({
		queryKey: backtestKeys.report(runId),
		queryFn: () => fetchBacktestReport(runId),
		enabled: runId.length > 0,
	});
}

export function useBacktestNav(runId: string) {
	return useQuery({
		queryKey: backtestKeys.nav(runId),
		queryFn: () => fetchBacktestNav(runId),
		enabled: runId.length > 0,
	});
}

export function useBacktestBenchmark(runId: string) {
	return useQuery({
		queryKey: backtestKeys.benchmark(runId),
		queryFn: () => fetchBacktestBenchmark(runId),
		enabled: runId.length > 0,
	});
}

export function useBacktestTrades(runId: string) {
	return useQuery({
		queryKey: backtestKeys.trades(runId),
		queryFn: () => fetchBacktestTrades(runId),
		enabled: runId.length > 0,
	});
}

export function useBacktestAudit(runId: string) {
	return useQuery({
		queryKey: backtestKeys.audit(runId),
		queryFn: () => fetchBacktestAudit(runId),
		enabled: runId.length > 0,
	});
}
