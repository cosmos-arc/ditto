import { useState } from "react";
import { cn } from "@/lib/utils";
import {
	Collapsible,
	CollapsibleContent,
	CollapsibleTrigger,
} from "@/components/ui/collapsible";

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
					"flex flex-col min-h-0",
					className,
				)}
				{...props}
			>
				{/* Header */}
				<CollapsibleTrigger
					data-slot="context-section-header"
					className="flex items-center justify-between py-[var(--space-8)] px-[var(--space-12)] shrink-0 cursor-pointer select-none hover:bg-(--color-surface-2) transition-colors duration-120 rounded-sm"
				>
					<span className="text-(--font-size-12) font-medium text-(--color-foreground-tertiary) uppercase tracking-wide">
						{title}
					</span>

					<div className="flex items-center gap-[var(--space-8)]">
						{count !== undefined && (
							<span className="text-(--font-size-10) text-(--color-foreground-tertiary) font-data">
								{count}
							</span>
						)}
						{action}
						<svg
							data-slot="context-section-chevron"
							className={cn(
								"size-3 text-(--color-foreground-tertiary) transition-transform duration-200",
								open && "rotate-90",
							)}
							viewBox="0 0 12 12"
							fill="none"
							xmlns="http://www.w3.org/2000/svg"
						>
							<path d="M4.5 2L8.5 6L4.5 10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
						</svg>
					</div>
				</CollapsibleTrigger>

				{/* Body */}
				<CollapsibleContent>
					<div
						data-slot="context-section-body"
						className="flex-1 overflow-y-auto px-[var(--space-12)]"
					>
						{children}
					</div>
				</CollapsibleContent>
			</div>
		</Collapsible>
	);
}

export { ContextSection };
export type { ContextSectionProps };
