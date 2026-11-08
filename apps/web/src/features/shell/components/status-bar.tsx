import { useQuery } from "@tanstack/react-query";
import { verifyBackendCompatibility } from "@/api/bootstrap";
import { CompatibilityError } from "@/api/compatibility";
import { isMockRuntime } from "@/api/runtime-config";

function formatTime(date: Date): string {
	return date.toLocaleString("zh-CN", { hour12: false });
}

/**
 * StatusBar -- VS Code-style bottom status bar.
 *
 * Fixed-positioned overlay floating outside the grid, matching prototype architecture.
 * Each page decides whether to render it via page-contracts `hasStatusBar`.
 * Pages that use StatusBar must add `pb-[var(--height-status-bar)]` to their layout root
 * to prevent content from being hidden behind the bar.
 */
export function StatusBar({
	spanRail = false,
	reserveRightRail = false,
}: {
	readonly spanRail?: boolean;
	readonly reserveRightRail?: boolean;
}) {
	const mock = isMockRuntime();
	const connection = useQuery({
		queryKey: ["shell", "api-connection"],
		queryFn: () => verifyBackendCompatibility({ release: import.meta.env.PROD }),
		enabled: !mock,
		retry: false,
		networkMode: "always",
		staleTime: 0,
		refetchInterval: 30_000,
		refetchOnWindowFocus: true,
		refetchOnReconnect: true,
	});
	const label = mock
		? "样例模式 · 未检查 API"
		: connection.isFetching
			? "正在检查 API"
			: connection.isError
				? connection.error instanceof CompatibilityError
					? "API 兼容性检查未通过"
					: "API 连接失败"
				: connection.isSuccess
					? `API 最近检查通过 · ${formatTime(new Date(connection.dataUpdatedAt))} 本地时间`
					: "API 尚未检查";

	return (
		<div
			data-slot="status-bar"
			role="status"
			aria-label="系统状态"
			className={
				"fixed bottom-0 z-50 " +
				(reserveRightRail
					? "left-0 right-(--width-rail) "
					: spanRail
						? "left-0 right-0 "
						: "left-(--width-rail) right-0 ") +
				"flex items-center gap-4 px-3 " +
				"h-[var(--height-status-bar)] " +
				"bg-(--color-surface-0) border-t border-(--color-border-subtle) " +
				"text-xs text-(--color-foreground-tertiary)"
			}
		>
			<span>{label}</span>
			<span className="flex-1" />
			{!mock && (
				<button
					type="button"
					aria-label="检查 API 连接"
					aria-disabled={connection.isFetching}
					onClick={() => {
						if (!connection.isFetching) void connection.refetch();
					}}
					className="rounded px-1 text-(--color-foreground-secondary) focus-visible:outline-2 focus-visible:outline-(--color-accent)"
				>
					重新检查
				</button>
			)}
		</div>
	);
}
