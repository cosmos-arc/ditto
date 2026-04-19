// AUTO-GENERATED — do not edit manually
// Run: bun run generate-contracts

/* ------------------------------------------------------------------ */
/*  Constants                                                          */
/* ------------------------------------------------------------------ */

export const PAGE_PATTERNS = [
  "global-command-center",
] as const;

export const SHELL_FAMILIES = [
  "command-center",
] as const;

export const PROTOTYPE_SOURCES = [
  "prototype-backed",
] as const;

export const SHELL_SLOT_MAP: Record<ShellFamily, string[]> = {
  "command-center": ["pulse", "main", "sidebar"],
};

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

export type PagePattern = (typeof PAGE_PATTERNS)[number];
export type ShellFamily = (typeof SHELL_FAMILIES)[number];
export type PrototypeSource = (typeof PROTOTYPE_SOURCES)[number];

export interface PageContract {
  route: string;
  pagePattern: PagePattern;
  shellFamily: ShellFamily;
  prototypeSource: PrototypeSource;
  prototypeRef?: string;
  requiredSlots: string[];
  requiredStates: string[];
  hasStatusBar?: boolean;
  sidebarCollapsible?: boolean;
  a11yRoles?: Record<string, string>;
  responsiveBehavior?: Record<string, string>;
}

/* ------------------------------------------------------------------ */
/*  Page Contracts                                                     */
/* ------------------------------------------------------------------ */

export const PAGE_CONTRACTS: readonly PageContract[] = [
  {
    route: "/",
    pagePattern: "global-command-center",
    shellFamily: "command-center",
    prototypeSource: "prototype-backed",
    prototypeRef: "docs/designs/specs/prototypes/page-home.html",
    requiredSlots: ["pulse", "main", "sidebar"],
    requiredStates: ["loading", "empty", "error", "stale", "no-alerts", "has-critical"],
    sidebarCollapsible: true,
    a11yRoles: {
      "pulse": "banner",
      "main": "main",
      "sidebar": "complementary",
    },
    responsiveBehavior: {
      "pulse": "collapsed",
      "sidebar": "overlay",
    },
  },
] as const satisfies readonly PageContract[];
