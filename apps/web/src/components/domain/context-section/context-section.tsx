import { useState } from "react";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { cn } from "@/lib/utils";

interface ContextSectionProps extends React.HTMLAttributes<HTMLDivElement> {
	readonly title: string;
	readonly count?: number;
	readonly defaultOpen?: boolean;
	readonly action?: React.ReactNode;
	readonly children: React.ReactNode;
}

function ContextSection({
	title,
	count,
	defaultOpen = true,
	action,
	children,
	className,
	...props
}: ContextSectionProps) {
	const [open, setOpen] = useState(defaultOpen);

	return (
		<Collapsible open={open} onOpenChange={setOpen}>
			<div
				data-slot="context-section"
				className={cn(
					"flex flex-col min-h-0 transition-colors duration-200",
					"hover:bg-[color-mix(in_oklch,var(--color-accent)_2%,var(--color-surface-panel-base))]",
					className,
				)}
				{...props}
			>
				{/* Header */}
				<CollapsibleTrigger
					data-slot="context-section-header"
					className="flex items-center justify-between shrink-0 cursor-pointer select-none hover:bg-(--color-surface-2) transition-colors duration-120 rounded-sm py-2 px-3"
				>
					<span className="text-sm font-medium text-(--color-foreground-tertiary) uppercase tracking-[0.04em]">
						{title}
					</span>

					<div className="flex items-center gap-2">
						{count !== undefined && (
							<span className="font-data text-sm tabular-nums text-(--color-foreground-tertiary) bg-(--color-surface-strip) rounded-[4px] flex items-center px-1.5 h-[18px]">
								{count}
							</span>
						)}
						{action}
						<svg
							data-slot="context-section-chevron"
							aria-hidden="true"
							focusable="false"
							className={cn(
								"size-3 text-(--color-foreground-tertiary) transition-transform duration-200",
								open && "rotate-90",
							)}
							viewBox="0 0 12 12"
							fill="none"
							xmlns="http://www.w3.org/2000/svg"
						>
							<path
								d="M4.5 2L8.5 6L4.5 10"
								stroke="currentColor"
								strokeWidth="1.5"
								strokeLinecap="round"
								strokeLinejoin="round"
							/>
						</svg>
					</div>
				</CollapsibleTrigger>

				{/* Body */}
				<CollapsibleContent>
					<div data-slot="context-section-body" className="flex-1 overflow-y-auto px-3">
						{children}
					</div>
				</CollapsibleContent>
			</div>
		</Collapsible>
	);
}

export type { ContextSectionProps };
export { ContextSection };
