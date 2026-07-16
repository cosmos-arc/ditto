import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { Slot } from "radix-ui"

import { cn } from "@/lib/utils"

const badgeVariants = cva(
  "group/badge inline-flex h-5 w-fit shrink-0 items-center justify-center gap-1 overflow-hidden rounded-(--radius-badge) border border-transparent px-2 py-0.5 text-xs font-medium whitespace-nowrap transition-all focus-visible:border-(--color-focus-border) focus-visible:ring-[3px] focus-visible:ring-(--color-focus-ring) has-data-[icon=inline-end]:pr-1.5 has-data-[icon=inline-start]:pl-1.5 aria-invalid:border-(--color-risk-critical-fg) aria-invalid:ring-(--color-risk-critical-bg) [&>svg]:pointer-events-none [&>svg]:size-3!",
  {
    variants: {
      variant: {
        default: "bg-(--color-accent) text-(--color-accent-fg) [a]:hover:bg-(--color-accent)",
        secondary:
          "bg-(--color-surface-panel-elevated) text-(--color-foreground-secondary) [a]:hover:bg-(--color-interaction-hover-subtle-bg)",
        destructive:
          "bg-(--color-risk-critical-bg) text-(--color-risk-critical-fg) focus-visible:ring-(--color-risk-critical-bg) [a]:hover:bg-(--color-risk-critical-bg)",
        outline:
          "border-(--color-border-default) text-(--color-foreground) [a]:hover:bg-(--color-interaction-hover-subtle-bg) [a]:hover:text-(--color-foreground-secondary)",
        ghost:
          "text-(--color-foreground-secondary) hover:bg-(--color-interaction-hover-subtle-bg) hover:text-(--color-foreground)",
        link: "text-(--color-accent) underline-offset-4 hover:underline",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
)

function Badge({
  className,
  variant = "default",
  asChild = false,
  ...props
}: React.ComponentProps<"span"> &
  VariantProps<typeof badgeVariants> & { asChild?: boolean }) {
  const Comp = asChild ? Slot.Root : "span"

  return (
    <Comp
      data-slot="badge"
      data-variant={variant}
      className={cn(badgeVariants({ variant }), className)}
      {...props}
    />
  )
}

export { Badge, badgeVariants }
