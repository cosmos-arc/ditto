import { ErrorBoundary as ReactErrorBoundary } from "react-error-boundary";
import { cn } from "@/lib/utils";

// ── ErrorState ──────────────────────────────────────────────

interface ErrorStateProps {
	readonly title?: string;
	readonly description?: string;
	readonly onRetry?: () => void;
	readonly className?: string;
}

function ErrorState({
	title = "加载失败",
	description,
	onRetry,
	className,
}: ErrorStateProps) {
	return (
		<div
			data-slot="error-state"
			className={cn(
				"flex flex-col items-center justify-center gap-3 py-8 text-center",
				className,
			)}
		>
			<span
				data-testid="error-state-icon"
				className={cn(
					"flex items-center justify-center w-10 h-10 rounded-full",
					"bg-(--color-led-error)/10",
				)}
			>
				<svg
					width="20"
					height="20"
					viewBox="0 0 20 20"
					fill="none"
					className="text-(--color-led-error)"
				>
					<path
						d="M10 6v5m0 3v.01M19 10a9 9 0 11-18 0 9 9 0 0118 0z"
						stroke="currentColor"
						strokeWidth="1.5"
						strokeLinecap="round"
						strokeLinejoin="round"
					/>
				</svg>
			</span>

			<div className="flex flex-col gap-1">
				<span className="text-[--text-md] font-medium text-(--color-foreground)">
					{title}
				</span>
				{description && (
					<span
						data-testid="error-state-description"
						className="text-[--text-sm] text-(--color-foreground-tertiary)"
					>
						{description}
					</span>
				)}
			</div>

			{onRetry && (
				<button
					type="button"
					onClick={onRetry}
					className={cn(
						"mt-1 rounded-md px-3 py-1.5 text-[--text-sm] font-medium",
						"bg-(--color-led-error)/10 text-(--color-led-error)",
						"transition-colors hover:bg-(--color-led-error)/20",
						"focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-(--color-led-error)/40",
					)}
				>
					重试
				</button>
			)}
		</div>
	);
}

// ── DittoErrorBoundary ──────────────────────────────────────

interface DittoErrorBoundaryProps {
	readonly children: React.ReactNode;
	readonly fallbackProps?: Omit<ErrorStateProps, "className">;
	readonly className?: string;
}

function DittoErrorBoundary({
	children,
	fallbackProps,
	className,
}: DittoErrorBoundaryProps) {
	return (
		<ReactErrorBoundary
			fallbackRender={({ resetErrorBoundary }) => (
				<ErrorState
					{...fallbackProps}
					onRetry={fallbackProps?.onRetry ?? resetErrorBoundary}
					className={className}
				/>
			)}
		>
			{children}
		</ReactErrorBoundary>
	);
}

export { ErrorState, DittoErrorBoundary };
