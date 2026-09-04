"use client";

import { Tooltip as TooltipPrimitive } from "radix-ui";
import type * as React from "react";
import { cn } from "@/lib/utils";

function DittoTooltip({ ...props }: React.ComponentProps<typeof TooltipPrimitive.Root>) {
	return (
		<TooltipPrimitive.Provider delayDuration={300}>
			<TooltipPrimitive.Root {...props} />
		</TooltipPrimitive.Provider>
	);
}

function DittoTooltipTrigger({ ...props }: React.ComponentProps<typeof TooltipPrimitive.Trigger>) {
	return <TooltipPrimitive.Trigger data-slot="tooltip-trigger" {...props} />;
}

function DittoTooltipContent({
	children,
	className,
	side = "top",
	sideOffset = 6,
	...props
}: React.ComponentProps<typeof TooltipPrimitive.Content>) {
	return (
		<TooltipPrimitive.Portal>
			<TooltipPrimitive.Content
				data-slot="tooltip"
				side={side}
				sideOffset={sideOffset}
				className={cn(
					"z-50 rounded-md px-3 py-1.5",
					"bg-(--color-surface-overlay) border border-(--color-border)",
					"text-xs leading-snug text-(--color-foreground-primary) max-w-[240px]",
					"shadow-[0_4px_12px_oklch(0_0_0/0.3)]",
					"duration-150",
					"data-[state=open]:animate-in data-[state=open]:fade-in-0",
					"data-[state=closed]:animate-out data-[state=closed]:fade-out-0",
					"fill-mode-forwards pointer-events-none",
					className,
				)}
				{...props}
			>
				{children}
			</TooltipPrimitive.Content>
		</TooltipPrimitive.Portal>
	);
}

export { DittoTooltip, DittoTooltipContent, DittoTooltipTrigger };
