import { cva, type VariantProps } from "class-variance-authority";
import { Slot } from "radix-ui";
import type * as React from "react";

import { cn } from "@/lib/utils";

const buttonVariants = cva(
	"group/button inline-flex shrink-0 items-center justify-center rounded-(--radius-btn) border border-transparent bg-clip-padding text-sm font-medium whitespace-nowrap transition-all outline-none select-none focus-visible:border-(--color-focus-border) focus-visible:ring-3 focus-visible:ring-(--color-focus-ring) active:not-aria-[haspopup]:translate-y-px disabled:pointer-events-none disabled:opacity-50 aria-invalid:border-(--color-risk-critical-fg) aria-invalid:ring-3 aria-invalid:ring-(--color-risk-critical-bg) [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
	{
		variants: {
			variant: {
				default: "bg-(--color-accent) text-(--color-accent-fg) [a]:hover:bg-(--color-accent)",
				outline:
					"border-(--color-border-default) bg-(--color-surface-panel-base) text-(--color-foreground-secondary) hover:bg-(--color-interaction-hover-subtle-bg) hover:text-(--color-foreground) aria-expanded:bg-(--color-interaction-active-bg) aria-expanded:text-(--color-foreground)",
				secondary:
					"bg-(--color-surface-panel-elevated) text-(--color-foreground-secondary) hover:bg-(--color-interaction-hover-subtle-bg) hover:text-(--color-foreground) aria-expanded:bg-(--color-interaction-active-bg) aria-expanded:text-(--color-foreground)",
				ghost:
					"text-(--color-foreground-secondary) hover:bg-(--color-interaction-hover-subtle-bg) hover:text-(--color-foreground) aria-expanded:bg-(--color-interaction-active-bg) aria-expanded:text-(--color-foreground)",
				destructive:
					"bg-(--color-risk-critical-bg) text-(--color-risk-critical-fg) hover:border-(--color-risk-critical-fg) hover:bg-(--color-risk-critical-bg) focus-visible:border-(--color-risk-critical-fg) focus-visible:ring-(--color-risk-critical-bg)",
				link: "text-(--color-accent) underline-offset-4 hover:underline",
			},
			size: {
				default: "h-8 gap-1.5 px-2.5 has-data-[icon=inline-end]:pr-2 has-data-[icon=inline-start]:pl-2",
				xs: "h-6 gap-1 rounded-[min(var(--radius-md),10px)] px-2 text-xs in-data-[slot=button-group]:rounded-lg has-data-[icon=inline-end]:pr-1.5 has-data-[icon=inline-start]:pl-1.5 [&_svg:not([class*='size-'])]:size-3",
				sm: "h-7 gap-1 rounded-[min(var(--radius-md),12px)] px-2.5 text-[0.8rem] in-data-[slot=button-group]:rounded-lg has-data-[icon=inline-end]:pr-1.5 has-data-[icon=inline-start]:pl-1.5 [&_svg:not([class*='size-'])]:size-3.5",
				lg: "h-9 gap-1.5 px-2.5 has-data-[icon=inline-end]:pr-3 has-data-[icon=inline-start]:pl-3",
				icon: "size-8",
				"icon-xs":
					"size-6 rounded-[min(var(--radius-md),10px)] in-data-[slot=button-group]:rounded-lg [&_svg:not([class*='size-'])]:size-3",
				"icon-sm": "size-7 rounded-[min(var(--radius-md),12px)] in-data-[slot=button-group]:rounded-lg",
				"icon-lg": "size-9",
			},
		},
		defaultVariants: {
			variant: "default",
			size: "default",
		},
	},
);

function Button({
	className,
	variant = "default",
	size = "default",
	asChild = false,
	...props
}: React.ComponentProps<"button"> &
	VariantProps<typeof buttonVariants> & {
		asChild?: boolean;
	}) {
	const Comp = asChild ? Slot.Root : "button";

	return (
		<Comp
			data-slot="button"
			data-variant={variant}
			data-size={size}
			className={cn(buttonVariants({ variant, size, className }))}
			{...props}
		/>
	);
}

export { Button, buttonVariants };
