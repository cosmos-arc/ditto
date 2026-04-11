import { useState, useEffect } from "react";

function formatTime(date: Date): string {
	const hours = date.getHours().toString().padStart(2, "0");
	const minutes = date.getMinutes().toString().padStart(2, "0");
	return `${hours}:${minutes}`;
}

/**
 * StatusBar -- VS Code-style bottom status bar.
 *
 * Displays LIVE indicator, connection status, latency, current time, and shortcut hint.
 * Self-contained with internal state for the clock.
 */
export function StatusBar() {
	const [time, setTime] = useState(() => formatTime(new Date()));

	useEffect(() => {
		const interval = setInterval(() => {
			setTime(formatTime(new Date()));
		}, 10_000);
		return () => clearInterval(interval);
	}, []);

	return (
		<div
			data-slot="status-bar"
			className={
				"flex items-center gap-4 px-3 " +
				"h-[var(--height-status-bar)] " +
				"bg-(--color-surface-0) border-t border-(--color-border-subtle) " +
				"text-xs text-(--color-foreground-tertiary)"
			}
		>
			<span className="flex items-center gap-1.5">
				<span
					className={
						"w-1.5 h-1.5 rounded-full " +
						"bg-(--color-status-led-healthy) " +
						"animate-[status-breathe_2s_ease-in-out_infinite]"
					}
				/>
				<span>LIVE</span>
			</span>
			<span>已连接</span>
			<span>12ms</span>
			<span className="flex-1" />
			<span>{time}</span>
			<span>⌘K 搜索</span>
		</div>
	);
}
