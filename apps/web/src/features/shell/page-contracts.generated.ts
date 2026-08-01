// AUTO-GENERATED — do not edit manually
// Run: bun run generate-contracts

/* ------------------------------------------------------------------ */
/*  Constants                                                          */
/* ------------------------------------------------------------------ */

export const PAGE_PATTERNS = [
  "analytical-overview",
  "studio-builder",
  "catalog-screener",
  "object-hub",
  "global-command-center",
  "ledger-execution-console",
  "config-integration-console",
  "queue-ops-console",
] as const;

export const SHELL_FAMILIES = [
  "radar",
  "studio",
  "catalog",
  "object-hub",
  "command-center",
  "analytical",
  "ops-console",
] as const;

export const PROTOTYPE_SOURCES = [
  "prototype-backed",
] as const;

export const SHELL_SLOT_MAP: Record<ShellFamily, string[]> = {
  "radar": ["strip", "main", "right-rail", "tab-band", "context-bar", "scope-strip", "bottom-tab-band"],
  "studio": ["header", "tabs", "source", "main", "inspector", "adoption", "graph", "actions", "modes"],
  "catalog": ["toolbar", "main", "detail", "header"],
  "object-hub": ["meta", "tabs", "main", "bottom"],
  "command-center": ["pulse", "main", "sidebar"],
  "analytical": ["strip", "main", "activity", "analysis"],
  "ops-console": ["health", "main", "detail"],
};

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

export type PagePattern = (typeof PAGE_PATTERNS)[number];
export type ShellFamily = (typeof SHELL_FAMILIES)[number];
export type PrototypeSource = (typeof PROTOTYPE_SOURCES)[number];

export type PageLandingRouteStatus = "missing" | "scaffolded" | "implemented";
export type PageLandingContractStatus = "missing" | "draft" | "generated" | "verified";
export type PageLandingOverlayStatus = "none" | "gallery-only" | "triggerable" | "implemented";
export type PageLandingVisualAuditStatus = "missing" | "queued" | "implemented" | "verified";
export type PageOverlayKind = "drawer" | "sheet" | "modal" | "alert-dialog" | "toast" | "inline";
export type PageOverlayCloseBehavior = "escape" | "outside-click" | "primary-action";

export interface PageLandingStatus {
  reactRouteStatus: PageLandingRouteStatus;
  featureModule: string;
  contractStatus: PageLandingContractStatus;
  overlayStatus: PageLandingOverlayStatus;
  visualAuditStatus: PageLandingVisualAuditStatus;
  reactTestRefs?: string[];
  reactComponentRefs?: string[];
}

export interface PageOverlayContract {
  id: string;
  kind: PageOverlayKind;
  blocking: boolean;
  requiredInDefaultFlow: boolean;
  trigger: { slot: string; action: string };
  prototypeSelector: string;
  reactComponent: string;
  closeBehavior: PageOverlayCloseBehavior[];
}

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
  landing?: PageLandingStatus;
  overlays?: PageOverlayContract[];
}

/* ------------------------------------------------------------------ */
/*  Page Contracts                                                     */
/* ------------------------------------------------------------------ */

export const PAGE_CONTRACTS: readonly PageContract[] = [
  {
    route: "/markets/a-shares",
    pagePattern: "analytical-overview",
    shellFamily: "radar",
    prototypeSource: "prototype-backed",
    prototypeRef: "docs/designs/specs/prototypes/page-a-shares.html",
    requiredSlots: ["strip", "main", "right-rail", "tab-band"],
    requiredStates: ["loading", "empty", "error", "stale", "market-paused"],
    landing: {
      "reactRouteStatus": "implemented",
      "featureModule": "src/features/markets",
      "contractStatus": "draft",
      "overlayStatus": "triggerable",
      "visualAuditStatus": "verified",
      "reactTestRefs": [
        "src/features/markets/components/a-shares-components.test.tsx"
      ],
      "reactComponentRefs": [
        "ASharesPage"
      ]
    },
    overlays: [
      {
        "id": "a-shares.northbound-detail",
        "kind": "drawer",
        "blocking": false,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-northbound-detail",
        "reactComponent": "PrototypeOnlyOverlay",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "a-shares.sector-detail",
        "kind": "drawer",
        "blocking": false,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-sector-detail",
        "reactComponent": "PrototypeOnlyOverlay",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "a-shares.filter-panel",
        "kind": "drawer",
        "blocking": false,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-filter-panel",
        "reactComponent": "PrototypeOnlyOverlay",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "a-shares.ai-analysis",
        "kind": "drawer",
        "blocking": false,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-ai-analysis",
        "reactComponent": "PrototypeOnlyOverlay",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      }
    ],
    a11yRoles: {
      "strip": "banner",
      "main": "main",
      "right-rail": "complementary",
      "tab-band": "navigation",
    },
    responsiveBehavior: {
      "strip": "collapsed",
      "right-rail": "overlay",
      "tab-band": "reflow",
    },
  },
  {
    route: "/platform/agents",
    pagePattern: "studio-builder",
    shellFamily: "studio",
    prototypeSource: "prototype-backed",
    prototypeRef: "docs/designs/specs/prototypes/page-agent-console-v2.html",
    requiredSlots: ["header", "tabs", "source", "main", "inspector"],
    requiredStates: ["loading", "empty", "error", "stale", "no-agents", "agent-running", "partial", "blocked", "waiting-approval", "guardrail-blocked", "quality-run"],
    hasStatusBar: true,
    landing: {
      "reactRouteStatus": "implemented",
      "featureModule": "src/features/platform",
      "contractStatus": "draft",
      "overlayStatus": "triggerable",
      "visualAuditStatus": "verified",
      "reactTestRefs": [
        "src/features/platform/components/platform-components.test.tsx"
      ],
      "reactComponentRefs": [
        "PlatformAgentsPage"
      ]
    },
    overlays: [
      {
        "id": "agent-console.plan-create",
        "kind": "sheet",
        "blocking": false,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-plan-create",
        "reactComponent": "PrototypeOnlyOverlay",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "agent-console.run-rerun",
        "kind": "sheet",
        "blocking": false,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-run-rerun",
        "reactComponent": "PrototypeOnlyOverlay",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "agent-console.approval-confirm",
        "kind": "modal",
        "blocking": true,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-approval-confirm",
        "reactComponent": "PrototypeOnlyOverlay",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "agent-console.tool-trace",
        "kind": "drawer",
        "blocking": false,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-tool-trace-detail",
        "reactComponent": "PrototypeOnlyOverlay",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "agent-console.artifact-preview",
        "kind": "drawer",
        "blocking": false,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "inspector",
          "action": "open-artifact"
        },
        "prototypeSelector": "#overlay-artifact-preview",
        "reactComponent": "PrototypeOnlyOverlay",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "agent-console.guardrail-detail",
        "kind": "drawer",
        "blocking": false,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "inspector",
          "action": "open-guardrail"
        },
        "prototypeSelector": "#overlay-guardrail-detail",
        "reactComponent": "PrototypeOnlyOverlay",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "agent-console.quality-run-create",
        "kind": "sheet",
        "blocking": false,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "create-quality-run"
        },
        "prototypeSelector": "#overlay-quality-run-create",
        "reactComponent": "PrototypeOnlyOverlay",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      }
    ],
    a11yRoles: {
      "header": "banner",
      "tabs": "tablist",
      "source": "complementary",
      "main": "main",
      "inspector": "complementary",
    },
    responsiveBehavior: {
      "header": "collapsed",
      "tabs": "reflow",
      "source": "collapsed",
      "inspector": "overlay",
    },
  },
  {
    route: "/research/alpha",
    pagePattern: "studio-builder",
    shellFamily: "studio",
    prototypeSource: "prototype-backed",
    prototypeRef: "docs/designs/specs/prototypes/page-alpha-explorer.html",
    requiredSlots: ["header", "source", "main", "inspector", "adoption", "graph"],
    requiredStates: ["loading", "empty", "error", "stale", "running", "partial", "blocked", "waiting-approval", "budget-exceeded"],
    landing: {
      "reactRouteStatus": "missing",
      "featureModule": "src/features/research",
      "contractStatus": "draft",
      "overlayStatus": "triggerable",
      "visualAuditStatus": "verified",
      "reactTestRefs": [],
      "reactComponentRefs": []
    },
    overlays: [
      {
        "id": "alpha-explorer.explore-run-create",
        "kind": "sheet",
        "blocking": false,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "header",
          "action": "start-run"
        },
        "prototypeSelector": "#overlay-explore-run-create",
        "reactComponent": "PrototypeOnlyOverlay",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "alpha-explorer.candidate-deep-dive",
        "kind": "drawer",
        "blocking": false,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-candidate"
        },
        "prototypeSelector": "#overlay-candidate-deep-dive",
        "reactComponent": "PrototypeOnlyOverlay",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "alpha-explorer.adoption-confirm",
        "kind": "modal",
        "blocking": true,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "inspector",
          "action": "approve-adoption"
        },
        "prototypeSelector": "#overlay-adoption-confirm",
        "reactComponent": "PrototypeOnlyOverlay",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "alpha-explorer.artifact-preview",
        "kind": "drawer",
        "blocking": false,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "graph",
          "action": "open-artifact"
        },
        "prototypeSelector": "#overlay-artifact-preview",
        "reactComponent": "PrototypeOnlyOverlay",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "alpha-explorer.guardrail-detail",
        "kind": "drawer",
        "blocking": false,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "adoption",
          "action": "open-guardrail"
        },
        "prototypeSelector": "#overlay-guardrail-detail",
        "reactComponent": "PrototypeOnlyOverlay",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "alpha-explorer.copilot-context",
        "kind": "sheet",
        "blocking": false,
        "requiredInDefaultFlow": false,
        "trigger": {
          "slot": "inspector",
          "action": "open-copilot-context"
        },
        "prototypeSelector": "#overlay-copilot-context",
        "reactComponent": "PrototypeOnlyOverlay",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      }
    ],
    a11yRoles: {
      "header": "banner",
      "source": "complementary",
      "main": "main",
      "inspector": "complementary",
      "adoption": "complementary",
      "graph": "region",
    },
    responsiveBehavior: {
      "header": "reflow",
      "source": "collapsed",
      "inspector": "overlay",
      "adoption": "collapsed",
      "graph": "collapsed",
    },
  },
  {
    route: "/research/backtest",
    pagePattern: "catalog-screener",
    shellFamily: "catalog",
    prototypeSource: "prototype-backed",
    prototypeRef: "docs/designs/specs/prototypes/page-backtest-list.html",
    requiredSlots: ["toolbar", "main", "detail"],
    requiredStates: ["loading", "empty", "error", "stale", "selected-backtest"],
    landing: {
      "reactRouteStatus": "implemented",
      "featureModule": "src/features/backtest",
      "contractStatus": "draft",
      "overlayStatus": "triggerable",
      "visualAuditStatus": "verified",
      "reactTestRefs": [
        "src/features/backtest/components/backtest-components.test.tsx"
      ],
      "reactComponentRefs": [
        "BacktestListPage"
      ]
    },
    overlays: [
      {
        "id": "backtest-list.backtest-compare",
        "kind": "drawer",
        "blocking": false,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-backtest-compare",
        "reactComponent": "PrototypeOnlyOverlay",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      }
    ],
    a11yRoles: {
      "toolbar": "region",
      "main": "main",
      "detail": "complementary",
    },
    responsiveBehavior: {
      "toolbar": "collapsed",
      "detail": "overlay",
    },
  },
  {
    route: "/research/backtest/$id",
    pagePattern: "object-hub",
    shellFamily: "object-hub",
    prototypeSource: "prototype-backed",
    prototypeRef: "docs/designs/specs/prototypes/page-backtest-result.html",
    requiredSlots: ["meta", "tabs", "main", "bottom"],
    requiredStates: ["loading", "empty", "error", "stale", "not-found"],
    landing: {
      "reactRouteStatus": "implemented",
      "featureModule": "src/features/backtest",
      "contractStatus": "draft",
      "overlayStatus": "triggerable",
      "visualAuditStatus": "verified",
      "reactTestRefs": [
        "src/features/backtest/components/info-level-annotations.test.tsx",
        "src/features/backtest/components/backtest-components.test.tsx"
      ],
      "reactComponentRefs": [
        "BacktestPage"
      ]
    },
    overlays: [
      {
        "id": "backtest-result.export",
        "kind": "sheet",
        "blocking": false,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-export",
        "reactComponent": "PrototypeOnlyOverlay",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "backtest-result.enable-signal",
        "kind": "modal",
        "blocking": true,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-enable-signal",
        "reactComponent": "PrototypeOnlyOverlay",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "backtest-result.ai-analysis",
        "kind": "drawer",
        "blocking": false,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-ai-analysis",
        "reactComponent": "PrototypeOnlyOverlay",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "backtest-result.compare-toast",
        "kind": "toast",
        "blocking": false,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-compare-toast",
        "reactComponent": "PrototypeOnlyOverlay",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "backtest-result.compare",
        "kind": "modal",
        "blocking": true,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-compare",
        "reactComponent": "PrototypeOnlyOverlay",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      }
    ],
    a11yRoles: {
      "meta": "banner",
      "tabs": "navigation",
      "main": "main",
      "bottom": "region",
    },
    responsiveBehavior: {
      "meta": "reflow",
      "tabs": "reflow",
      "bottom": "collapsed",
    },
  },
  {
    route: "/markets",
    pagePattern: "analytical-overview",
    shellFamily: "radar",
    prototypeSource: "prototype-backed",
    prototypeRef: "docs/designs/specs/prototypes/page-cross-market.html",
    requiredSlots: ["context-bar", "scope-strip", "main", "right-rail", "bottom-tab-band"],
    requiredStates: ["loading", "empty", "error", "stale", "market-closed"],
    hasStatusBar: true,
    landing: {
      "reactRouteStatus": "implemented",
      "featureModule": "src/features/markets",
      "contractStatus": "draft",
      "overlayStatus": "triggerable",
      "visualAuditStatus": "verified",
      "reactTestRefs": [
        "src/features/markets/components/markets-page.test.tsx",
        "src/features/markets/components/markets-components.test.tsx"
      ],
      "reactComponentRefs": [
        "MarketsPage"
      ]
    },
    overlays: [
      {
        "id": "cross-market.market-depth",
        "kind": "sheet",
        "blocking": false,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-market-depth",
        "reactComponent": "PrototypeOnlyOverlay",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "cross-market.index-components",
        "kind": "sheet",
        "blocking": false,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-index-components",
        "reactComponent": "PrototypeOnlyOverlay",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "cross-market.filter-panel",
        "kind": "drawer",
        "blocking": false,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-filter-panel",
        "reactComponent": "PrototypeOnlyOverlay",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "cross-market.event-detail",
        "kind": "drawer",
        "blocking": false,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-event-detail",
        "reactComponent": "PrototypeOnlyOverlay",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "cross-market.pin-viewpoint",
        "kind": "drawer",
        "blocking": false,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-pin-viewpoint",
        "reactComponent": "PrototypeOnlyOverlay",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      }
    ],
    a11yRoles: {
      "context-bar": "status",
      "scope-strip": "status",
      "main": "main",
      "right-rail": "complementary",
      "bottom-tab-band": "region",
    },
    responsiveBehavior: {
      "context-bar": "collapsed",
      "scope-strip": "collapsed",
      "right-rail": "overlay",
      "bottom-tab-band": "reflow",
    },
  },
  {
    route: "/research/experiments/new",
    pagePattern: "studio-builder",
    shellFamily: "studio",
    prototypeSource: "prototype-backed",
    prototypeRef: "docs/contracts/pages/experiment-create.contract.json",
    requiredSlots: ["main", "actions"],
    requiredStates: ["loading", "empty", "error", "stale", "preflight-ready", "preflight-blocked", "launch-unknown"],
    hasStatusBar: true,
    landing: {
      "reactRouteStatus": "implemented",
      "featureModule": "src/features/research",
      "contractStatus": "generated",
      "overlayStatus": "none",
      "visualAuditStatus": "queued",
      "reactTestRefs": [
        "src/features/research/components/experiment-create-page.test.tsx"
      ],
      "reactComponentRefs": [
        "ExperimentCreatePage"
      ]
    },
    a11yRoles: {
      "main": "main",
      "actions": "toolbar",
    },
    responsiveBehavior: {
      "actions": "reflow",
    },
  },
  {
    route: "/research/experiments/$id",
    pagePattern: "object-hub",
    shellFamily: "object-hub",
    prototypeSource: "prototype-backed",
    prototypeRef: "docs/contracts/pages/experiment-detail.contract.json",
    requiredSlots: ["meta", "main", "bottom"],
    requiredStates: ["loading", "empty", "error", "stale", "running", "paused", "failed", "completed", "partial-resource-error"],
    hasStatusBar: true,
    landing: {
      "reactRouteStatus": "implemented",
      "featureModule": "src/features/research",
      "contractStatus": "generated",
      "overlayStatus": "none",
      "visualAuditStatus": "queued",
      "reactTestRefs": [
        "src/features/research/components/experiment-detail-page.test.tsx",
        "src/features/research/components/candidate-selection-holdout.test.tsx"
      ],
      "reactComponentRefs": [
        "ExperimentDetailPage"
      ]
    },
    a11yRoles: {
      "meta": "banner",
      "main": "main",
      "bottom": "status",
    },
    responsiveBehavior: {
      "meta": "reflow",
      "bottom": "collapsed",
    },
  },
  {
    route: "/research/experiments",
    pagePattern: "catalog-screener",
    shellFamily: "catalog",
    prototypeSource: "prototype-backed",
    prototypeRef: "docs/designs/specs/prototypes/page-experiment-list.html",
    requiredSlots: ["header", "main", "detail"],
    requiredStates: ["loading", "empty", "error", "stale", "experiment-running"],
    hasStatusBar: true,
    landing: {
      "reactRouteStatus": "implemented",
      "featureModule": "src/features/research",
      "contractStatus": "draft",
      "overlayStatus": "triggerable",
      "visualAuditStatus": "verified",
      "reactTestRefs": [
        "src/features/research/components/research-components.test.tsx"
      ],
      "reactComponentRefs": [
        "ExperimentListPage"
      ]
    },
    overlays: [
      {
        "id": "experiment-list.experiment-detail",
        "kind": "drawer",
        "blocking": false,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-experiment-detail",
        "reactComponent": "PrototypeOnlyOverlay",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      }
    ],
    a11yRoles: {
      "header": "toolbar",
      "main": "main",
      "detail": "complementary",
    },
    responsiveBehavior: {
      "header": "reflow",
      "detail": "overlay",
    },
  },
  {
    route: "/research/factors/$id",
    pagePattern: "object-hub",
    shellFamily: "object-hub",
    prototypeSource: "prototype-backed",
    prototypeRef: "docs/designs/specs/prototypes/page-factor-analysis.html",
    requiredSlots: ["meta", "tabs", "main", "bottom"],
    requiredStates: ["loading", "empty", "error", "stale", "not-found"],
    landing: {
      "reactRouteStatus": "implemented",
      "featureModule": "src/features/research",
      "contractStatus": "draft",
      "overlayStatus": "triggerable",
      "visualAuditStatus": "verified",
      "reactTestRefs": [
        "src/features/research/components/info-level-annotations.test.tsx",
        "src/features/research/components/factor-components.test.tsx"
      ],
      "reactComponentRefs": [
        "FactorPage"
      ]
    },
    overlays: [
      {
        "id": "factor-analysis.add-backtest",
        "kind": "sheet",
        "blocking": false,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-add-backtest",
        "reactComponent": "PrototypeOnlyOverlay",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "factor-analysis.add-experiment",
        "kind": "sheet",
        "blocking": false,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-add-experiment",
        "reactComponent": "PrototypeOnlyOverlay",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "factor-analysis.ai-analysis",
        "kind": "drawer",
        "blocking": false,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-ai-analysis",
        "reactComponent": "PrototypeOnlyOverlay",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "factor-analysis.diagnostic-detail",
        "kind": "modal",
        "blocking": true,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-diagnostic-detail",
        "reactComponent": "PrototypeOnlyOverlay",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      }
    ],
    a11yRoles: {
      "meta": "banner",
      "tabs": "navigation",
      "main": "main",
      "bottom": "region",
    },
    responsiveBehavior: {
      "meta": "reflow",
      "tabs": "reflow",
      "bottom": "collapsed",
    },
  },
  {
    route: "/research/factors",
    pagePattern: "catalog-screener",
    shellFamily: "catalog",
    prototypeSource: "prototype-backed",
    prototypeRef: "docs/designs/specs/prototypes/page-factor-list.html",
    requiredSlots: ["toolbar", "main", "detail"],
    requiredStates: ["loading", "empty", "error", "stale", "selected-factor"],
    landing: {
      "reactRouteStatus": "implemented",
      "featureModule": "src/features/research",
      "contractStatus": "draft",
      "overlayStatus": "triggerable",
      "visualAuditStatus": "verified",
      "reactTestRefs": [
        "src/features/research/components/research-components.test.tsx",
        "src/features/research/components/factor-components.test.tsx",
        "src/features/research/components/factor-table.test.tsx"
      ],
      "reactComponentRefs": [
        "FactorListPage"
      ]
    },
    overlays: [
      {
        "id": "factor-list.factor-compare",
        "kind": "drawer",
        "blocking": false,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-factor-compare",
        "reactComponent": "PrototypeOnlyOverlay",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      }
    ],
    a11yRoles: {
      "toolbar": "region",
      "main": "main",
      "detail": "complementary",
    },
    responsiveBehavior: {
      "toolbar": "collapsed",
      "detail": "overlay",
    },
  },
  {
    route: "/",
    pagePattern: "global-command-center",
    shellFamily: "command-center",
    prototypeSource: "prototype-backed",
    prototypeRef: "docs/designs/specs/prototypes/page-home.html",
    requiredSlots: ["pulse", "main", "sidebar"],
    requiredStates: ["loading", "empty", "error", "stale", "no-alerts", "has-critical", "daily-brief-stale", "pending-approvals", "priority-findings"],
    sidebarCollapsible: true,
    landing: {
      "reactRouteStatus": "implemented",
      "featureModule": "src/features/home",
      "contractStatus": "draft",
      "overlayStatus": "triggerable",
      "visualAuditStatus": "verified",
      "reactTestRefs": [
        "src/features/home/components/home-components.test.tsx",
        "src/features/home/hooks/home-hooks.test.tsx"
      ],
      "reactComponentRefs": [
        "HomePage"
      ]
    },
    overlays: [
      {
        "id": "home.signal-detail",
        "kind": "drawer",
        "blocking": false,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-signal-detail",
        "reactComponent": "PrototypeOnlyOverlay",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "home.order-confirm",
        "kind": "modal",
        "blocking": true,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-order-confirm",
        "reactComponent": "PrototypeOnlyOverlay",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "home.edit-workspace",
        "kind": "sheet",
        "blocking": false,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-edit-workspace",
        "reactComponent": "PrototypeOnlyOverlay",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "home.ai-advice",
        "kind": "drawer",
        "blocking": false,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-ai-advice",
        "reactComponent": "PrototypeOnlyOverlay",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      }
    ],
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
  {
    route: "/instruments/$id",
    pagePattern: "object-hub",
    shellFamily: "object-hub",
    prototypeSource: "prototype-backed",
    prototypeRef: "docs/designs/specs/prototypes/page-instrument-hub.html",
    requiredSlots: ["meta", "tabs", "main", "bottom"],
    requiredStates: ["loading", "empty", "error", "stale", "not-found"],
    hasStatusBar: true,
    landing: {
      "reactRouteStatus": "implemented",
      "featureModule": "src/features/instruments",
      "contractStatus": "draft",
      "overlayStatus": "triggerable",
      "visualAuditStatus": "verified",
      "reactTestRefs": [
        "src/features/instruments/components/info-level-annotations.test.tsx",
        "src/features/instruments/components/instrument-components.test.tsx"
      ],
      "reactComponentRefs": [
        "InstrumentHubPage"
      ]
    },
    overlays: [
      {
        "id": "instrument-hub.chart-toolbar",
        "kind": "drawer",
        "blocking": false,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-chart-toolbar",
        "reactComponent": "PrototypeOnlyOverlay",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "instrument-hub.news-detail",
        "kind": "drawer",
        "blocking": false,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-news-detail",
        "reactComponent": "PrototypeOnlyOverlay",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "instrument-hub.announcement-detail",
        "kind": "drawer",
        "blocking": false,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-announcement-detail",
        "reactComponent": "PrototypeOnlyOverlay",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "instrument-hub.add-watchlist",
        "kind": "drawer",
        "blocking": false,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-add-watchlist",
        "reactComponent": "PrototypeOnlyOverlay",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "instrument-hub.send-research",
        "kind": "drawer",
        "blocking": false,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-send-research",
        "reactComponent": "PrototypeOnlyOverlay",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "instrument-hub.halt-detail",
        "kind": "drawer",
        "blocking": false,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-halt-detail",
        "reactComponent": "PrototypeOnlyOverlay",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      }
    ],
    a11yRoles: {
      "meta": "banner",
      "tabs": "navigation",
      "main": "main",
      "bottom": "region",
    },
    responsiveBehavior: {
      "meta": "reflow",
      "tabs": "reflow",
      "bottom": "collapsed",
    },
  },
  {
    route: "/markets/calendar",
    pagePattern: "catalog-screener",
    shellFamily: "catalog",
    prototypeSource: "prototype-backed",
    prototypeRef: "docs/designs/specs/prototypes/page-markets-calendar.html",
    requiredSlots: ["toolbar", "main", "detail"],
    requiredStates: ["loading", "empty", "error", "stale", "holiday"],
    landing: {
      "reactRouteStatus": "implemented",
      "featureModule": "src/features/markets",
      "contractStatus": "draft",
      "overlayStatus": "triggerable",
      "visualAuditStatus": "verified",
      "reactTestRefs": [
        "src/features/markets/components/calendar-components.test.tsx"
      ],
      "reactComponentRefs": [
        "CalendarPage"
      ]
    },
    overlays: [
      {
        "id": "markets-calendar.event-detail",
        "kind": "drawer",
        "blocking": false,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-event-detail",
        "reactComponent": "PrototypeOnlyOverlay",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "markets-calendar.reminder",
        "kind": "sheet",
        "blocking": false,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-reminder",
        "reactComponent": "PrototypeOnlyOverlay",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "markets-calendar.intelligence",
        "kind": "modal",
        "blocking": true,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-intelligence",
        "reactComponent": "PrototypeOnlyOverlay",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      }
    ],
    a11yRoles: {
      "toolbar": "region",
      "main": "main",
      "detail": "complementary",
    },
    responsiveBehavior: {
      "toolbar": "collapsed",
      "detail": "overlay",
    },
  },
  {
    route: "/markets/intelligence",
    pagePattern: "analytical-overview",
    shellFamily: "analytical",
    prototypeSource: "prototype-backed",
    prototypeRef: "docs/designs/specs/prototypes/page-markets-intelligence.html",
    requiredSlots: ["strip", "main", "activity", "analysis"],
    requiredStates: ["loading", "empty", "error", "stale", "no-briefs"],
    hasStatusBar: true,
    sidebarCollapsible: true,
    landing: {
      "reactRouteStatus": "implemented",
      "featureModule": "src/features/markets",
      "contractStatus": "draft",
      "overlayStatus": "triggerable",
      "visualAuditStatus": "verified",
      "reactTestRefs": [
        "src/features/markets/components/intelligence-page.test.tsx",
        "src/features/markets/components/intelligence-components.test.tsx"
      ],
      "reactComponentRefs": [
        "IntelligencePage"
      ]
    },
    overlays: [
      {
        "id": "markets-intelligence.intelligence-detail",
        "kind": "drawer",
        "blocking": false,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-intelligence-detail",
        "reactComponent": "PrototypeOnlyOverlay",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "markets-intelligence.custom-filter",
        "kind": "drawer",
        "blocking": false,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-custom-filter",
        "reactComponent": "PrototypeOnlyOverlay",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "markets-intelligence.bookmark-success",
        "kind": "toast",
        "blocking": false,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-bookmark-success",
        "reactComponent": "PrototypeOnlyOverlay",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "markets-intelligence.delete-confirm",
        "kind": "modal",
        "blocking": true,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-delete-confirm",
        "reactComponent": "PrototypeOnlyOverlay",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "markets-intelligence.send-to-copilot",
        "kind": "drawer",
        "blocking": false,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-send-to-copilot",
        "reactComponent": "PrototypeOnlyOverlay",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      }
    ],
    a11yRoles: {
      "strip": "banner",
      "main": "main",
      "activity": "complementary",
      "analysis": "complementary",
    },
    responsiveBehavior: {
      "strip": "collapsed",
      "activity": "collapsed",
      "analysis": "overlay",
    },
  },
  {
    route: "/markets/screener",
    pagePattern: "catalog-screener",
    shellFamily: "catalog",
    prototypeSource: "prototype-backed",
    prototypeRef: "docs/designs/specs/prototypes/page-markets-screener.html",
    requiredSlots: ["toolbar", "main", "detail"],
    requiredStates: ["loading", "empty", "error", "stale", "selected-row"],
    landing: {
      "reactRouteStatus": "implemented",
      "featureModule": "src/features/screener",
      "contractStatus": "draft",
      "overlayStatus": "triggerable",
      "visualAuditStatus": "verified",
      "reactTestRefs": [
        "src/features/screener/components/info-level-annotations.test.tsx",
        "src/features/screener/components/screener-components.test.tsx"
      ],
      "reactComponentRefs": [
        "ScreenerPage"
      ]
    },
    overlays: [
      {
        "id": "markets-screener.save-preset",
        "kind": "modal",
        "blocking": true,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-save-preset",
        "reactComponent": "PrototypeOnlyOverlay",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "markets-screener.column-manage",
        "kind": "sheet",
        "blocking": false,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-column-manage",
        "reactComponent": "PrototypeOnlyOverlay",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "markets-screener.compare",
        "kind": "sheet",
        "blocking": false,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-compare",
        "reactComponent": "PrototypeOnlyOverlay",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "markets-screener.generate-pool",
        "kind": "sheet",
        "blocking": false,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-generate-pool",
        "reactComponent": "PrototypeOnlyOverlay",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "markets-screener.export",
        "kind": "drawer",
        "blocking": false,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-export",
        "reactComponent": "PrototypeOnlyOverlay",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      }
    ],
    a11yRoles: {
      "toolbar": "region",
      "main": "main",
      "detail": "complementary",
    },
    responsiveBehavior: {
      "toolbar": "collapsed",
      "detail": "overlay",
    },
  },
  {
    route: "/trading/orders",
    pagePattern: "ledger-execution-console",
    shellFamily: "ops-console",
    prototypeSource: "prototype-backed",
    prototypeRef: "docs/designs/specs/prototypes/page-orders-ledger.html",
    requiredSlots: ["health", "main", "detail"],
    requiredStates: ["loading", "empty", "error", "stale", "selected-row", "order-active"],
    hasStatusBar: true,
    landing: {
      "reactRouteStatus": "implemented",
      "featureModule": "src/features/trading",
      "contractStatus": "draft",
      "overlayStatus": "triggerable",
      "visualAuditStatus": "verified",
      "reactTestRefs": [
        "src/features/trading/components/orders-components.test.tsx"
      ],
      "reactComponentRefs": [
        "OrdersPage"
      ]
    },
    overlays: [
      {
        "id": "orders-ledger.cancel-confirm",
        "kind": "modal",
        "blocking": true,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-cancel-confirm",
        "reactComponent": "PrototypeOnlyOverlay",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "orders-ledger.retry-submit",
        "kind": "modal",
        "blocking": true,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-retry-submit",
        "reactComponent": "PrototypeOnlyOverlay",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "orders.order-detail",
        "kind": "drawer",
        "blocking": false,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "select-order"
        },
        "prototypeSelector": "#overlay-order-detail",
        "reactComponent": "OrderDetailPanel",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "orders.batch-cancel",
        "kind": "modal",
        "blocking": true,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "health",
          "action": "batch-cancel"
        },
        "prototypeSelector": "#overlay-batch-cancel",
        "reactComponent": "BatchCancelDialog",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      }
    ],
    a11yRoles: {
      "health": "banner",
      "main": "main",
      "detail": "complementary",
    },
    responsiveBehavior: {
      "health": "collapsed",
      "detail": "overlay",
    },
  },
  {
    route: "/platform/settings",
    pagePattern: "config-integration-console",
    shellFamily: "ops-console",
    prototypeSource: "prototype-backed",
    prototypeRef: "docs/designs/specs/prototypes/page-platform-settings.html",
    requiredSlots: ["health", "main", "detail"],
    requiredStates: ["loading", "empty", "error", "stale", "settings-dirty", "ai-policy-dirty", "guardrail-failed", "tool-permission-selected"],
    hasStatusBar: true,
    landing: {
      "reactRouteStatus": "implemented",
      "featureModule": "src/features/platform",
      "contractStatus": "draft",
      "overlayStatus": "triggerable",
      "visualAuditStatus": "verified",
      "reactTestRefs": [
        "src/features/platform/components/platform-components.test.tsx",
        "src/features/platform/hooks/platform-hooks.test.tsx"
      ],
      "reactComponentRefs": [
        "PlatformSettingsPage"
      ]
    },
    overlays: [
      {
        "id": "platform-settings.datasource-test",
        "kind": "sheet",
        "blocking": false,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-datasource-test",
        "reactComponent": "PrototypeOnlyOverlay",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "platform-settings.broker-test",
        "kind": "sheet",
        "blocking": false,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-broker-test",
        "reactComponent": "PrototypeOnlyOverlay",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "platform-settings.save-config",
        "kind": "modal",
        "blocking": true,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-save-config",
        "reactComponent": "PrototypeOnlyOverlay",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "platform-settings.reset-config",
        "kind": "modal",
        "blocking": true,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-reset-config",
        "reactComponent": "PrototypeOnlyOverlay",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      }
    ],
    a11yRoles: {
      "health": "banner",
      "main": "main",
      "detail": "complementary",
    },
    responsiveBehavior: {
      "health": "collapsed",
      "detail": "overlay",
    },
  },
  {
    route: "/platform",
    pagePattern: "queue-ops-console",
    shellFamily: "ops-console",
    prototypeSource: "prototype-backed",
    prototypeRef: "docs/designs/specs/prototypes/page-platform.html",
    requiredSlots: ["health", "main", "detail"],
    requiredStates: ["loading", "empty", "error", "stale", "pipeline-running"],
    hasStatusBar: true,
    landing: {
      "reactRouteStatus": "implemented",
      "featureModule": "src/features/platform",
      "contractStatus": "draft",
      "overlayStatus": "triggerable",
      "visualAuditStatus": "verified",
      "reactTestRefs": [
        "src/features/platform/components/platform-components.test.tsx",
        "src/features/platform/components/info-level-annotations.test.tsx",
        "src/features/platform/hooks/platform-hooks.test.tsx"
      ],
      "reactComponentRefs": [
        "PlatformPage"
      ]
    },
    overlays: [
      {
        "id": "platform.pipeline-rerun",
        "kind": "sheet",
        "blocking": false,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-pipeline-rerun",
        "reactComponent": "PrototypeOnlyOverlay",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "platform.alert-handle",
        "kind": "sheet",
        "blocking": false,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-alert-handle",
        "reactComponent": "PrototypeOnlyOverlay",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "platform.task-detail",
        "kind": "drawer",
        "blocking": false,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-task-detail",
        "reactComponent": "PrototypeOnlyOverlay",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      }
    ],
    a11yRoles: {
      "health": "banner",
      "main": "main",
      "detail": "complementary",
    },
    responsiveBehavior: {
      "health": "collapsed",
      "detail": "overlay",
    },
  },
  {
    route: "/trading/portfolio",
    pagePattern: "analytical-overview",
    shellFamily: "analytical",
    prototypeSource: "prototype-backed",
    prototypeRef: "docs/designs/specs/prototypes/page-portfolio.html",
    requiredSlots: ["strip", "main", "activity", "analysis"],
    requiredStates: ["loading", "empty", "error", "stale", "no-positions"],
    hasStatusBar: true,
    landing: {
      "reactRouteStatus": "implemented",
      "featureModule": "src/features/trading",
      "contractStatus": "draft",
      "overlayStatus": "triggerable",
      "visualAuditStatus": "verified",
      "reactTestRefs": [
        "src/features/trading/components/trading-components.test.tsx",
        "src/features/trading/components/positions-summary.test.tsx"
      ],
      "reactComponentRefs": [
        "PortfolioPage"
      ]
    },
    overlays: [
      {
        "id": "portfolio.position-detail",
        "kind": "drawer",
        "blocking": false,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-position-detail",
        "reactComponent": "PrototypeOnlyOverlay",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "portfolio.trade-detail",
        "kind": "modal",
        "blocking": true,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-trade-detail",
        "reactComponent": "PrototypeOnlyOverlay",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "portfolio.confirm-close-all",
        "kind": "modal",
        "blocking": true,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-confirm-close-all",
        "reactComponent": "PrototypeOnlyOverlay",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      }
    ],
    a11yRoles: {
      "strip": "banner",
      "main": "main",
      "activity": "complementary",
      "analysis": "complementary",
    },
    responsiveBehavior: {
      "strip": "collapsed",
      "activity": "collapsed",
      "analysis": "overlay",
    },
  },
  {
    route: "/research/regime",
    pagePattern: "analytical-overview",
    shellFamily: "analytical",
    prototypeSource: "prototype-backed",
    prototypeRef: "docs/designs/specs/prototypes/page-regime-monitor.html",
    requiredSlots: ["strip", "main", "activity", "analysis"],
    requiredStates: ["loading", "empty", "error", "stale", "regime-transition"],
    hasStatusBar: true,
    landing: {
      "reactRouteStatus": "implemented",
      "featureModule": "src/features/research",
      "contractStatus": "draft",
      "overlayStatus": "triggerable",
      "visualAuditStatus": "verified",
      "reactTestRefs": [
        "src/features/research/components/info-level-annotations.test.tsx",
        "src/features/research/components/regime-components.test.tsx"
      ],
      "reactComponentRefs": [
        "RegimePage"
      ]
    },
    overlays: [
      {
        "id": "regime-monitor.ai-regime",
        "kind": "drawer",
        "blocking": false,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-ai-regime",
        "reactComponent": "PrototypeOnlyOverlay",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      }
    ],
    a11yRoles: {
      "strip": "banner",
      "main": "main",
      "activity": "complementary",
      "analysis": "complementary",
    },
    responsiveBehavior: {
      "strip": "collapsed",
      "activity": "collapsed",
      "analysis": "overlay",
    },
  },
  {
    route: "/research",
    pagePattern: "analytical-overview",
    shellFamily: "analytical",
    prototypeSource: "prototype-backed",
    prototypeRef: "docs/designs/specs/prototypes/page-research.html",
    requiredSlots: ["strip", "main", "activity", "analysis"],
    requiredStates: ["loading", "empty", "error", "stale", "no-runs"],
    landing: {
      "reactRouteStatus": "implemented",
      "featureModule": "src/features/research",
      "contractStatus": "draft",
      "overlayStatus": "triggerable",
      "visualAuditStatus": "verified",
      "reactTestRefs": [
        "src/features/research/components/info-level-annotations.test.tsx",
        "src/features/research/components/research-components.test.tsx"
      ],
      "reactComponentRefs": [
        "ResearchPage"
      ]
    },
    overlays: [
      {
        "id": "research.new-backtest",
        "kind": "sheet",
        "blocking": false,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-new-backtest",
        "reactComponent": "PrototypeOnlyOverlay",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "research.new-strategy",
        "kind": "sheet",
        "blocking": false,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-new-strategy",
        "reactComponent": "PrototypeOnlyOverlay",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "research.new-experiment",
        "kind": "sheet",
        "blocking": false,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-new-experiment",
        "reactComponent": "PrototypeOnlyOverlay",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "research.run-detail",
        "kind": "drawer",
        "blocking": false,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-run-detail",
        "reactComponent": "PrototypeOnlyOverlay",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "research.review-action",
        "kind": "drawer",
        "blocking": false,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-review-action",
        "reactComponent": "PrototypeOnlyOverlay",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      }
    ],
    a11yRoles: {
      "strip": "banner",
      "main": "main",
      "activity": "complementary",
      "analysis": "complementary",
    },
    responsiveBehavior: {
      "strip": "collapsed",
      "activity": "collapsed",
      "analysis": "overlay",
    },
  },
  {
    route: "/research/reviews/$id",
    pagePattern: "object-hub",
    shellFamily: "object-hub",
    prototypeSource: "prototype-backed",
    prototypeRef: "docs/contracts/pages/review-detail.contract.json",
    requiredSlots: ["meta", "main", "bottom"],
    requiredStates: ["loading", "empty", "error", "stale", "hard-gate-blocked", "review-pending", "approved", "published", "rejected"],
    landing: {
      "reactRouteStatus": "implemented",
      "featureModule": "src/features/research",
      "contractStatus": "generated",
      "overlayStatus": "implemented",
      "visualAuditStatus": "queued",
      "reactTestRefs": [
        "src/features/research/components/review-detail-page.test.tsx"
      ],
      "reactComponentRefs": [
        "ReviewDetailPage"
      ]
    },
    a11yRoles: {
      "meta": "banner",
      "main": "main",
      "bottom": "region",
    },
    responsiveBehavior: {
      "meta": "reflow",
      "bottom": "overlay",
    },
  },
  {
    route: "/research/reviews",
    pagePattern: "catalog-screener",
    shellFamily: "catalog",
    prototypeSource: "prototype-backed",
    prototypeRef: "docs/contracts/pages/review-list.contract.json",
    requiredSlots: ["toolbar", "main", "detail"],
    requiredStates: ["loading", "empty", "error", "stale", "packet-missing", "approved-awaiting-publish"],
    landing: {
      "reactRouteStatus": "implemented",
      "featureModule": "src/features/research",
      "contractStatus": "generated",
      "overlayStatus": "none",
      "visualAuditStatus": "queued",
      "reactTestRefs": [
        "src/features/research/components/review-queue-page.test.tsx"
      ],
      "reactComponentRefs": [
        "ReviewQueuePage"
      ]
    },
    a11yRoles: {
      "toolbar": "toolbar",
      "main": "main",
      "detail": "complementary",
    },
    responsiveBehavior: {
      "toolbar": "reflow",
      "detail": "overlay",
    },
  },
  {
    route: "/trading/risk",
    pagePattern: "analytical-overview",
    shellFamily: "analytical",
    prototypeSource: "prototype-backed",
    prototypeRef: "docs/designs/specs/prototypes/page-risk-center.html",
    requiredSlots: ["strip", "main", "activity", "analysis"],
    requiredStates: ["loading", "empty", "error", "stale", "breach-active"],
    hasStatusBar: true,
    landing: {
      "reactRouteStatus": "implemented",
      "featureModule": "src/features/trading",
      "contractStatus": "draft",
      "overlayStatus": "triggerable",
      "visualAuditStatus": "verified",
      "reactTestRefs": [
        "src/features/trading/components/risk-components.test.tsx",
        "src/features/trading/components/risk-breach-detail.test.tsx"
      ],
      "reactComponentRefs": [
        "RiskPage"
      ]
    },
    overlays: [
      {
        "id": "risk-center.stress-config",
        "kind": "drawer",
        "blocking": false,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-stress-config",
        "reactComponent": "PrototypeOnlyOverlay",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "risk.breach-detail",
        "kind": "drawer",
        "blocking": false,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "select-breach"
        },
        "prototypeSelector": "#overlay-breach-detail",
        "reactComponent": "BreachDetailContent",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "risk.rule-editor",
        "kind": "sheet",
        "blocking": true,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "analysis",
          "action": "edit-rule"
        },
        "prototypeSelector": "#overlay-rule-editor",
        "reactComponent": "RiskRuleEditorSheet",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      }
    ],
    a11yRoles: {
      "strip": "banner",
      "main": "main",
      "activity": "complementary",
      "analysis": "complementary",
    },
    responsiveBehavior: {
      "strip": "collapsed",
      "activity": "collapsed",
      "analysis": "overlay",
    },
  },
  {
    route: "/trading/signals",
    pagePattern: "queue-ops-console",
    shellFamily: "ops-console",
    prototypeSource: "prototype-backed",
    prototypeRef: "docs/designs/specs/prototypes/page-signals-inbox.html",
    requiredSlots: ["health", "main", "detail"],
    requiredStates: ["loading", "empty", "error", "stale", "selected-row", "sheet-open", "ai-review", "risk-pass", "risk-warn", "risk-block", "evidence-open"],
    hasStatusBar: true,
    landing: {
      "reactRouteStatus": "implemented",
      "featureModule": "src/features/trading",
      "contractStatus": "draft",
      "overlayStatus": "triggerable",
      "visualAuditStatus": "verified",
      "reactTestRefs": [
        "src/features/trading/components/signals-components.test.tsx"
      ],
      "reactComponentRefs": [
        "SignalsPage"
      ]
    },
    overlays: [
      {
        "id": "signals.order-confirm",
        "kind": "sheet",
        "blocking": true,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "detail",
          "action": "confirm-signal"
        },
        "prototypeSelector": "#overlay-order-confirm",
        "reactComponent": "SignalDetailPanel",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "signals.ai-read",
        "kind": "modal",
        "blocking": true,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "detail",
          "action": "ai-read"
        },
        "prototypeSelector": "#overlay-ai-read",
        "reactComponent": "SignalAiReadDialog",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "signals-inbox.batch-confirm",
        "kind": "modal",
        "blocking": true,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-batch-confirm",
        "reactComponent": "PrototypeOnlyOverlay",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "signals-inbox.signal-confirm-to-order",
        "kind": "modal",
        "blocking": true,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-signal-confirm-to-order",
        "reactComponent": "PrototypeOnlyOverlay",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      }
    ],
    a11yRoles: {
      "health": "banner",
      "main": "main",
      "detail": "complementary",
    },
    responsiveBehavior: {
      "health": "collapsed",
      "detail": "overlay",
    },
  },
  {
    route: "/research/strategies/$id",
    pagePattern: "object-hub",
    shellFamily: "object-hub",
    prototypeSource: "prototype-backed",
    prototypeRef: "docs/designs/specs/prototypes/page-strategies-detail.html",
    requiredSlots: ["meta", "tabs", "main", "bottom"],
    requiredStates: ["loading", "empty", "error", "stale", "not-found", "optimization-pending", "optimization-simulating", "optimization-simulated", "optimization-approved", "optimization-expired"],
    landing: {
      "reactRouteStatus": "implemented",
      "featureModule": "src/features/strategy",
      "contractStatus": "draft",
      "overlayStatus": "triggerable",
      "visualAuditStatus": "verified",
      "reactTestRefs": [
        "src/features/strategy/components/info-level-annotations.test.tsx",
        "src/features/strategy/components/strategy-detail-components.test.tsx"
      ],
      "reactComponentRefs": [
        "StrategyDetailPage"
      ]
    },
    overlays: [
      {
        "id": "strategies-detail.delete-strategy",
        "kind": "modal",
        "blocking": true,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-delete-strategy",
        "reactComponent": "PrototypeOnlyOverlay",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "strategies-detail.submit-backtest",
        "kind": "sheet",
        "blocking": false,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-submit-backtest",
        "reactComponent": "PrototypeOnlyOverlay",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "strategies-detail.copy-strategy",
        "kind": "sheet",
        "blocking": false,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-copy-strategy",
        "reactComponent": "PrototypeOnlyOverlay",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "strategies-detail.version-rollback",
        "kind": "modal",
        "blocking": true,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-version-rollback",
        "reactComponent": "PrototypeOnlyOverlay",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      }
    ],
    a11yRoles: {
      "meta": "banner",
      "tabs": "navigation",
      "main": "main",
      "bottom": "region",
    },
    responsiveBehavior: {
      "meta": "reflow",
      "tabs": "reflow",
      "bottom": "collapsed",
    },
  },
  {
    route: "/research/strategies",
    pagePattern: "catalog-screener",
    shellFamily: "catalog",
    prototypeSource: "prototype-backed",
    prototypeRef: "docs/designs/specs/prototypes/page-strategy-list.html",
    requiredSlots: ["toolbar", "main", "detail"],
    requiredStates: ["loading", "empty", "error", "stale", "selected-strategy"],
    landing: {
      "reactRouteStatus": "implemented",
      "featureModule": "src/features/strategy",
      "contractStatus": "draft",
      "overlayStatus": "triggerable",
      "visualAuditStatus": "verified",
      "reactTestRefs": [
        "src/features/strategy/components/strategy-components.test.tsx"
      ],
      "reactComponentRefs": [
        "StrategyListPage"
      ]
    },
    overlays: [
      {
        "id": "strategy-list.strategy-clone",
        "kind": "sheet",
        "blocking": false,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-strategy-clone",
        "reactComponent": "PrototypeOnlyOverlay",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "strategy-list.strategy-delete",
        "kind": "modal",
        "blocking": true,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-strategy-delete",
        "reactComponent": "PrototypeOnlyOverlay",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      }
    ],
    a11yRoles: {
      "toolbar": "region",
      "main": "main",
      "detail": "complementary",
    },
    responsiveBehavior: {
      "toolbar": "collapsed",
      "detail": "overlay",
    },
  },
  {
    route: "/research/strategies/$id/studio",
    pagePattern: "studio-builder",
    shellFamily: "studio",
    prototypeSource: "prototype-backed",
    prototypeRef: "docs/designs/specs/prototypes/page-strategy-studio.html",
    requiredSlots: ["source", "main", "inspector", "modes"],
    requiredStates: ["loading", "empty", "error", "stale", "no-session", "running", "guided", "agent-running", "waiting-approval", "blocked"],
    hasStatusBar: true,
    landing: {
      "reactRouteStatus": "implemented",
      "featureModule": "src/features/strategy",
      "contractStatus": "draft",
      "overlayStatus": "triggerable",
      "visualAuditStatus": "verified",
      "reactTestRefs": [
        "src/features/strategy/components/info-level-annotations.test.tsx",
        "src/features/strategy/components/strategy-components.test.tsx",
        "src/features/strategy/components/studio-mode-bar.test.tsx"
      ],
      "reactComponentRefs": [
        "StrategyPage"
      ]
    },
    overlays: [
      {
        "id": "strategy-studio.delete-strategy",
        "kind": "modal",
        "blocking": true,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-delete-strategy",
        "reactComponent": "PrototypeOnlyOverlay",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "strategy-studio.save-strategy",
        "kind": "sheet",
        "blocking": false,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-save-strategy",
        "reactComponent": "PrototypeOnlyOverlay",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "strategy-studio.validation-toast",
        "kind": "toast",
        "blocking": false,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-validation-toast",
        "reactComponent": "PrototypeOnlyOverlay",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "strategy-studio.backtest-config",
        "kind": "drawer",
        "blocking": false,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-backtest-config",
        "reactComponent": "PrototypeOnlyOverlay",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "strategy-studio.factor-preview",
        "kind": "drawer",
        "blocking": false,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-factor-preview",
        "reactComponent": "PrototypeOnlyOverlay",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      }
    ],
    a11yRoles: {
      "source": "complementary",
      "main": "main",
      "inspector": "complementary",
      "modes": "navigation",
    },
    responsiveBehavior: {
      "source": "collapsed",
      "inspector": "overlay",
      "modes": "reflow",
    },
  },
  {
    route: "/trading",
    pagePattern: "analytical-overview",
    shellFamily: "analytical",
    prototypeSource: "prototype-backed",
    prototypeRef: "docs/designs/specs/prototypes/page-trading-overview.html",
    requiredSlots: ["strip", "main", "activity", "analysis"],
    requiredStates: ["loading", "empty", "error", "stale", "market-closed"],
    hasStatusBar: true,
    landing: {
      "reactRouteStatus": "implemented",
      "featureModule": "src/features/trading",
      "contractStatus": "draft",
      "overlayStatus": "triggerable",
      "visualAuditStatus": "verified",
      "reactTestRefs": [
        "src/features/trading/components/trading-components.test.tsx"
      ],
      "reactComponentRefs": [
        "TradingPage"
      ]
    },
    overlays: [
      {
        "id": "trading-overview.pause-trading",
        "kind": "modal",
        "blocking": true,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-pause-trading",
        "reactComponent": "PrototypeOnlyOverlay",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "trading-overview.position-detail",
        "kind": "drawer",
        "blocking": false,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-position-detail",
        "reactComponent": "PrototypeOnlyOverlay",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "trading-overview.risk-alert-detail",
        "kind": "drawer",
        "blocking": false,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-risk-alert-detail",
        "reactComponent": "PrototypeOnlyOverlay",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "trading-overview.limit-status",
        "kind": "drawer",
        "blocking": false,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-limit-status",
        "reactComponent": "PrototypeOnlyOverlay",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      }
    ],
    a11yRoles: {
      "strip": "banner",
      "main": "main",
      "activity": "complementary",
      "analysis": "complementary",
    },
    responsiveBehavior: {
      "strip": "collapsed",
      "activity": "collapsed",
      "analysis": "overlay",
    },
  },
  {
    route: "/research/universes",
    pagePattern: "catalog-screener",
    shellFamily: "catalog",
    prototypeSource: "prototype-backed",
    prototypeRef: "docs/designs/specs/prototypes/page-universe-list.html",
    requiredSlots: ["toolbar", "main", "detail"],
    requiredStates: ["loading", "empty", "error", "stale", "selected-universe"],
    landing: {
      "reactRouteStatus": "implemented",
      "featureModule": "src/features/research",
      "contractStatus": "draft",
      "overlayStatus": "triggerable",
      "visualAuditStatus": "verified",
      "reactTestRefs": [
        "src/features/research/components/research-components.test.tsx"
      ],
      "reactComponentRefs": [
        "UniverseListPage"
      ]
    },
    overlays: [
      {
        "id": "universe-list.universe-edit",
        "kind": "sheet",
        "blocking": false,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-universe-edit",
        "reactComponent": "PrototypeOnlyOverlay",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "universe-list.universe-delete",
        "kind": "modal",
        "blocking": true,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-universe-delete",
        "reactComponent": "PrototypeOnlyOverlay",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      }
    ],
    a11yRoles: {
      "toolbar": "region",
      "main": "main",
      "detail": "complementary",
    },
    responsiveBehavior: {
      "toolbar": "collapsed",
      "detail": "overlay",
    },
  },
  {
    route: "/markets/watchlist",
    pagePattern: "catalog-screener",
    shellFamily: "catalog",
    prototypeSource: "prototype-backed",
    prototypeRef: "docs/designs/specs/prototypes/page-watchlist.html",
    requiredSlots: ["toolbar", "main", "detail"],
    requiredStates: ["loading", "empty", "error", "stale", "no-symbols"],
    landing: {
      "reactRouteStatus": "implemented",
      "featureModule": "src/features/markets",
      "contractStatus": "draft",
      "overlayStatus": "triggerable",
      "visualAuditStatus": "verified",
      "reactTestRefs": [
        "src/features/markets/components/markets-components.test.tsx"
      ],
      "reactComponentRefs": [
        "WatchlistPage"
      ]
    },
    overlays: [
      {
        "id": "watchlist.add-instrument",
        "kind": "sheet",
        "blocking": false,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-add-instrument",
        "reactComponent": "PrototypeOnlyOverlay",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "watchlist.bulk-delete",
        "kind": "modal",
        "blocking": true,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-bulk-delete",
        "reactComponent": "PrototypeOnlyOverlay",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      }
    ],
    a11yRoles: {
      "toolbar": "region",
      "main": "main",
      "detail": "complementary",
    },
    responsiveBehavior: {
      "toolbar": "collapsed",
      "detail": "overlay",
    },
  },
] as const satisfies readonly PageContract[];
