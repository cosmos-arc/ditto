import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const DEFAULT_TABLE_COLUMNS = 4;
const DEFAULT_TABLE_ROWS = 3;
const DEFAULT_PANEL_ROWS = 3;

const shimmerBase =
	"rounded-sm bg-[linear-gradient(90deg,var(--color-surface-2)_25%,var(--color-surface-4)_50%,var(--color-surface-2)_75%)] bg-[length:200%_100%] animate-[skeleton-shimmer_1.5s_ease-in-out_infinite]";

const skeletonVariants = cva("w-full", {
	variants: {
		variant: {
			panel: "flex flex-col gap-2",
			table: "flex flex-col gap-2",
			card: "flex flex-col gap-3",
			metric: "flex flex-col gap-2",
			chart: "",
		},
	},
	defaultVariants: {
		variant: "panel",
	},
});

interface LoadingSkeletonProps
	extends React.HTMLAttributes<HTMLDivElement>,
		VariantProps<typeof skeletonVariants> {
	readonly rows?: number;
	readonly columns?: number;
}

function ShimmerBar({
	className,
	"data-testid": testId,
}: {
	readonly className?: string;
	readonly "data-testid"?: string;
}) {
	return <div data-testid={testId} className={cn(shimmerBase, className)} />;
}

function LoadingSkeleton({
	variant = "panel",
	rows,
	columns,
	className,
	...props
}: LoadingSkeletonProps) {
	return (
		<div
			data-slot="loading-skeleton"
			data-variant={variant}
			data-testid="loading-skeleton"
			className={cn(skeletonVariants({ variant }), className)}
			{...props}
		>
			{variant === "panel" && <PanelSkeleton rows={rows ?? DEFAULT_PANEL_ROWS} />}
			{variant === "table" && (
				<TableSkeleton
					columns={columns ?? DEFAULT_TABLE_COLUMNS}
					rows={rows ?? DEFAULT_TABLE_ROWS}
				/>
			)}
			{variant === "card" && <CardSkeleton />}
			{variant === "metric" && <MetricSkeleton />}
			{variant === "chart" && <ChartSkeleton />}
		</div>
	);
}

function PanelSkeleton({ rows }: { readonly rows: number }) {
	return (
		<>
			<ShimmerBar
				data-testid="skeleton-header"
				className="w-[40%] h-4"
			/>
			{Array.from({ length: rows }, (_, i) => (
				<ShimmerBar
					key={i}
					data-testid="skeleton-row"
					className="w-full h-3"
				/>
			))}
		</>
	);
}

function TableSkeleton({ columns, rows }: { readonly columns: number; readonly rows: number }) {
	return (
		<>
			<div data-testid="skeleton-table-header" className="flex gap-2">
				{Array.from({ length: columns }, (_, i) => (
					<ShimmerBar
						key={`header-${i}`}
						data-testid="skeleton-table-header-cell"
						className="flex-1 h-3"
					/>
				))}
			</div>
			{Array.from({ length: rows }, (_, i) => (
				<div key={`row-${i}`} data-testid="skeleton-table-row" className="flex gap-2">
					{Array.from({ length: columns }, (_, j) => (
						<ShimmerBar
							key={`row-${i}-cell-${j}`}
							className="flex-1 h-3"
						/>
					))}
				</div>
			))}
		</>
	);
}

function CardSkeleton() {
	return (
		<>
			<ShimmerBar
				data-testid="skeleton-card-title"
				className="w-[40%] h-4"
			/>
			<ShimmerBar
				data-testid="skeleton-card-content"
				className="w-full h-24"
			/>
		</>
	);
}

function MetricSkeleton() {
	return (
		<>
			<ShimmerBar
				data-testid="skeleton-metric-label"
				className="w-[60%] h-[10px]"
			/>
			<ShimmerBar
				data-testid="skeleton-metric-value"
				className="w-[40%] h-4"
			/>
		</>
	);
}

function ChartSkeleton() {
	return (
		<ShimmerBar
			data-testid="skeleton-chart"
			className="w-full h-40"
		/>
	);
}

export { LoadingSkeleton, skeletonVariants };
