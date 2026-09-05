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
  "queue-ops-console",
  "config-integration-console",
] as const;

export const SHELL_FAMILIES = [
  "analytical",
  "studio",
  "catalog",
  "object-hub",
  "radar",
  "command-center",
  "ops-console",
] as const;

export const PROTOTYPE_SOURCES = [
  "prototype-backed",
] as const;

export const SHELL_SLOT_MAP: Record<ShellFamily, string[]> = {
  "analytical": ["strip", "main", "activity", "analysis"],
  "studio": ["shell", "header", "tabs", "source", "main", "inspector", "modes", "logs"],
  "catalog": ["toolbar", "main", "detail"],
  "object-hub": ["header", "meta", "tabs", "main", "bottom", "sidebar"],
  "radar": ["context-bar", "scope-strip", "main", "right-rail", "status"],
  "command-center": ["pulse", "main", "sidebar"],
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
export type PageOverlayKind = "drawer" | "sheet" | "modal" | "alert-dialog" | "toast" | "inline";
export type PageOverlayCloseBehavior = "escape" | "outside-click" | "primary-action";

export interface PageLandingStatus {
  reactRouteStatus: PageLandingRouteStatus;
  featureModule: string;
  contractStatus: PageLandingContractStatus;
  overlayStatus: PageLandingOverlayStatus;
  prototypeVerified: boolean;
  reactParityVerified: boolean;
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
    shellFamily: "analytical",
    prototypeSource: "prototype-backed",
    prototypeRef: "docs/designs/specs/prototypes/page-a-shares.html",
    requiredSlots: ["strip", "main", "activity"],
    requiredStates: ["loading", "empty", "error", "stale", "no-active-stocks", "exchange-empty", "price-evidence-unavailable"],
    landing: {
      "reactRouteStatus": "implemented",
      "featureModule": "src/features/markets",
      "contractStatus": "verified",
      "overlayStatus": "triggerable",
      "prototypeVerified": true,
      "reactParityVerified": true,
      "reactTestRefs": [
        "src/features/markets/components/a-shares-components.test.tsx",
        "src/features/markets/components/info-level-annotations.test.tsx"
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
          "slot": "strip",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-northbound-detail",
        "reactComponent": "ASharesOverlay",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "a-shares.sector-detail",
        "kind": "sheet",
        "blocking": false,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-sector-detail",
        "reactComponent": "ASharesOverlay",
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
          "slot": "strip",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-filter-panel",
        "reactComponent": "ASharesOverlay",
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
          "slot": "activity",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-ai-analysis",
        "reactComponent": "ASharesOverlay",
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
    },
    responsiveBehavior: {
      "strip": "collapsed",
      "activity": "overlay",
    },
  },
  {
    route: "/system/approvals",
    pagePattern: "studio-builder",
    shellFamily: "studio",
    prototypeSource: "prototype-backed",
    prototypeRef: "docs/designs/specs/prototypes/page-agent-console-v2.html",
    requiredSlots: ["shell", "header", "tabs", "source", "main", "inspector"],
    requiredStates: ["loading", "empty", "error", "stale", "disabled", "degraded", "running", "partial", "blocked", "waiting-approval", "approval-expired", "guardrail-blocked", "cancelled", "failed", "completed", "reconnecting"],
    hasStatusBar: true,
    landing: {
      "reactRouteStatus": "implemented",
      "featureModule": "src/features/agent",
      "contractStatus": "verified",
      "overlayStatus": "triggerable",
      "prototypeVerified": true,
      "reactParityVerified": true,
      "reactTestRefs": [
        "src/features/agent/components/agent-console-page.test.tsx",
        "src/features/agent/components/agent-overlays.test.tsx",
        "src/features/agent/components/agent-author-preview.test.tsx"
      ],
      "reactComponentRefs": [
        "AgentConsolePage"
      ]
    },
    overlays: [
      {
        "id": "agent-console.run-create",
        "kind": "sheet",
        "blocking": false,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-run-create",
        "reactComponent": "AgentRunCreateSheet",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "agent-console.run-cancel",
        "kind": "modal",
        "blocking": true,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-run-cancel",
        "reactComponent": "AgentRunCancelDialog",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "agent-console.approval-exact-action",
        "kind": "modal",
        "blocking": true,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-approval-exact-action",
        "reactComponent": "AgentApprovalExactActionDialog",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "agent-console.evidence-detail",
        "kind": "drawer",
        "blocking": false,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-evidence-detail",
        "reactComponent": "AgentEvidenceDetailDrawer",
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
        "reactComponent": "AgentArtifactPreviewDrawer",
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
        "reactComponent": "AgentGuardrailDetailDrawer",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "agent-console.campaign-draft",
        "kind": "sheet",
        "blocking": false,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "create-campaign"
        },
        "prototypeSelector": "#overlay-campaign-draft",
        "reactComponent": "AgentCampaignDraftSheet",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "agent-console.campaign-approval",
        "kind": "modal",
        "blocking": true,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "approve-campaign"
        },
        "prototypeSelector": "#overlay-campaign-approval",
        "reactComponent": "AgentCampaignApprovalDialog",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "agent-console.campaign-cancel",
        "kind": "modal",
        "blocking": true,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "cancel-campaign"
        },
        "prototypeSelector": "#overlay-campaign-cancel",
        "reactComponent": "AgentCampaignCancelDialog",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      }
    ],
    a11yRoles: {
      "shell": "region",
      "header": "banner",
      "tabs": "tablist",
      "source": "complementary",
      "main": "main",
      "inspector": "complementary",
    },
    responsiveBehavior: {
      "shell": "reflow",
      "header": "collapsed",
      "tabs": "reflow",
      "source": "collapsed",
      "main": "reflow",
      "inspector": "overlay",
    },
  },
  {
    route: "/research/backtests",
    pagePattern: "catalog-screener",
    shellFamily: "catalog",
    prototypeSource: "prototype-backed",
    prototypeRef: "docs/designs/specs/prototypes/page-backtest-list.html",
    requiredSlots: ["toolbar", "main", "detail"],
    requiredStates: ["loading", "empty", "error", "stale", "selected-backtest", "filtered-results", "filtered-empty", "run-queued", "run-running", "run-completed", "run-failed", "benchmark-unpublished"],
    landing: {
      "reactRouteStatus": "implemented",
      "featureModule": "src/features/backtest",
      "contractStatus": "verified",
      "overlayStatus": "triggerable",
      "prototypeVerified": true,
      "reactParityVerified": true,
      "reactTestRefs": [
        "src/features/backtest/components/backtest-list-page.test.tsx",
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
          "slot": "toolbar",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-backtest-compare",
        "reactComponent": "BacktestCompareOverlay",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      }
    ],
    a11yRoles: {
      "toolbar": "toolbar",
      "main": "main",
      "detail": "complementary",
    },
    responsiveBehavior: {
      "toolbar": "reflow",
      "detail": "unchanged",
    },
  },
  {
    route: "/research/backtests/$id",
    pagePattern: "object-hub",
    shellFamily: "object-hub",
    prototypeSource: "prototype-backed",
    prototypeRef: "docs/designs/specs/prototypes/page-backtest-result.html",
    requiredSlots: ["header", "meta", "tabs", "main", "bottom"],
    requiredStates: ["loading", "empty", "error", "stale", "selected-nav-tab", "selected-report-tab", "selected-trades-tab", "selected-audit-tab", "run-unavailable", "report-unavailable", "performance-unpublished", "nav-unavailable", "benchmark-unpublished", "benchmark-unavailable", "trades-empty", "trades-unavailable", "audit-empty", "audit-unavailable"],
    landing: {
      "reactRouteStatus": "implemented",
      "featureModule": "src/features/backtest",
      "contractStatus": "verified",
      "overlayStatus": "triggerable",
      "prototypeVerified": true,
      "reactParityVerified": true,
      "reactTestRefs": [
        "src/features/backtest/components/backtest-page-workspace.test.tsx",
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
          "slot": "header",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-export",
        "reactComponent": "BacktestOverlays",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "backtest-result.enable-signal",
        "kind": "alert-dialog",
        "blocking": true,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "header",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-enable-signal",
        "reactComponent": "BacktestOverlays",
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
          "slot": "header",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-ai-analysis",
        "reactComponent": "BacktestOverlays",
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
          "slot": "header",
          "action": "toggle"
        },
        "prototypeSelector": "#overlay-compare-toast",
        "reactComponent": "BacktestOverlays",
        "closeBehavior": [
          "primary-action"
        ]
      },
      {
        "id": "backtest-result.compare",
        "kind": "modal",
        "blocking": false,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "header",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-compare",
        "reactComponent": "BacktestOverlays",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      }
    ],
    a11yRoles: {
      "header": "banner",
      "meta": "complementary",
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
    requiredSlots: ["context-bar", "scope-strip", "main", "right-rail", "status"],
    requiredStates: ["loading", "empty", "error", "stale", "catalog-empty", "partial-page", "price-evidence-unavailable", "identity-only"],
    hasStatusBar: true,
    landing: {
      "reactRouteStatus": "implemented",
      "featureModule": "src/features/markets",
      "contractStatus": "verified",
      "overlayStatus": "triggerable",
      "prototypeVerified": true,
      "reactParityVerified": true,
      "reactTestRefs": [
        "src/features/markets/components/markets-page.test.tsx",
        "src/features/markets/components/info-level-annotations.test.tsx"
      ],
      "reactComponentRefs": [
        "MarketsPage"
      ]
    },
    overlays: [
      {
        "id": "cross-market.market-depth",
        "kind": "drawer",
        "blocking": false,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-market-depth",
        "reactComponent": "MarketsOverviewOverlay",
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
          "slot": "scope-strip",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-index-components",
        "reactComponent": "MarketsOverviewOverlay",
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
          "slot": "scope-strip",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-filter-panel",
        "reactComponent": "MarketsOverviewOverlay",
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
          "slot": "right-rail",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-event-detail",
        "reactComponent": "MarketsOverviewOverlay",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "cross-market.pin-viewpoint",
        "kind": "inline",
        "blocking": false,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "context-bar",
          "action": "toggle"
        },
        "prototypeSelector": "#overlay-pin-viewpoint",
        "reactComponent": "MarketsOverviewOverlay",
        "closeBehavior": [
          "primary-action"
        ]
      }
    ],
    a11yRoles: {
      "context-bar": "status",
      "scope-strip": "status",
      "main": "main",
      "right-rail": "complementary",
      "status": "status",
    },
    responsiveBehavior: {
      "context-bar": "collapsed",
      "scope-strip": "collapsed",
      "right-rail": "overlay",
      "status": "reflow",
    },
  },
  {
    route: "/research/experiments/new",
    pagePattern: "studio-builder",
    shellFamily: "studio",
    prototypeSource: "prototype-backed",
    prototypeRef: "docs/designs/specs/prototypes/page-strategy-studio.html",
    requiredSlots: ["header", "modes", "source", "main", "inspector", "logs"],
    requiredStates: ["loading", "empty", "error", "stale", "invalid-json", "preflight-not-run", "preflight-ready", "preflight-blocked", "preflight-stale", "confirmation-required", "launch-pending", "launch-rejected", "launch-outcome-unknown"],
    hasStatusBar: true,
    landing: {
      "reactRouteStatus": "implemented",
      "featureModule": "src/features/research",
      "contractStatus": "verified",
      "overlayStatus": "none",
      "prototypeVerified": true,
      "reactParityVerified": true,
      "reactTestRefs": [
        "src/features/research/components/experiment-create-page.test.tsx"
      ],
      "reactComponentRefs": [
        "ExperimentCreatePage"
      ]
    },
    overlays: [],
    a11yRoles: {
      "header": "banner",
      "modes": "navigation",
      "source": "complementary",
      "main": "main",
      "inspector": "complementary",
      "logs": "log",
    },
    responsiveBehavior: {
      "modes": "unchanged",
      "source": "unchanged",
      "inspector": "unchanged",
      "logs": "unchanged",
    },
  },
  {
    route: "/research/experiments/$id",
    pagePattern: "object-hub",
    shellFamily: "object-hub",
    prototypeSource: "prototype-backed",
    prototypeRef: "docs/designs/specs/prototypes/page-strategies-detail.html",
    requiredSlots: ["header", "meta", "tabs", "main", "bottom"],
    requiredStates: ["loading", "empty", "error", "stale", "selected-candidates-tab", "selected-validation-tab", "selected-evidence-tab", "selected-candidate-evidence-tab", "detail-unavailable", "partial-resource-error", "selection-evidence-publishing", "candidate-evidence-stale", "holdout-consumed", "control-outcome-unknown"],
    landing: {
      "reactRouteStatus": "implemented",
      "featureModule": "src/features/research",
      "contractStatus": "verified",
      "overlayStatus": "none",
      "prototypeVerified": true,
      "reactParityVerified": true,
      "reactTestRefs": [
        "src/features/research/components/experiment-detail-page.test.tsx",
        "src/features/research/components/candidate-selection-holdout.test.tsx",
        "src/features/research/components/experiment-run-recovery.test.tsx",
        "src/features/research/components/experiment-validation-view.test.tsx"
      ],
      "reactComponentRefs": [
        "ExperimentDetailPage"
      ]
    },
    overlays: [],
    a11yRoles: {
      "header": "banner",
      "meta": "complementary",
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
    route: "/research/experiments",
    pagePattern: "catalog-screener",
    shellFamily: "catalog",
    prototypeSource: "prototype-backed",
    prototypeRef: "docs/designs/specs/prototypes/page-experiment-list.html",
    requiredSlots: ["toolbar", "main", "detail"],
    requiredStates: ["loading", "empty", "error", "stale", "experiment-running", "experiment-queued", "experiment-completed", "experiment-failed", "filtered-empty", "selected-experiment", "detail-drawer-open"],
    landing: {
      "reactRouteStatus": "implemented",
      "featureModule": "src/features/research",
      "contractStatus": "verified",
      "overlayStatus": "triggerable",
      "prototypeVerified": true,
      "reactParityVerified": true,
      "reactTestRefs": [
        "src/features/research/components/experiment-list-page-workspace.test.tsx",
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
          "slot": "detail",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-experiment-detail",
        "reactComponent": "ExperimentListPage",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      }
    ],
    a11yRoles: {
      "toolbar": "toolbar",
      "main": "main",
      "detail": "complementary",
    },
    responsiveBehavior: {
      "toolbar": "reflow",
      "detail": "unchanged",
    },
  },
  {
    route: "/research/factors/$id",
    pagePattern: "object-hub",
    shellFamily: "object-hub",
    prototypeSource: "prototype-backed",
    prototypeRef: "docs/designs/specs/prototypes/page-factor-analysis.html",
    requiredSlots: ["header", "meta", "main", "sidebar"],
    requiredStates: ["loading", "empty", "error", "stale", "evidence-scope-missing", "diagnostics-ready", "handoff-open", "ai-governance-open", "diagnostic-detail-open"],
    landing: {
      "reactRouteStatus": "implemented",
      "featureModule": "src/features/research",
      "contractStatus": "verified",
      "overlayStatus": "triggerable",
      "prototypeVerified": true,
      "reactParityVerified": true,
      "reactTestRefs": [
        "src/features/research/components/factor-page-workspace.test.tsx",
        "src/features/research/components/factor-diagnostics.test.tsx",
        "src/features/research/components/info-level-annotations.test.tsx"
      ],
      "reactComponentRefs": [
        "FactorPage",
        "FactorDiagnosticsView"
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
        "reactComponent": "FactorPageOverlays",
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
        "reactComponent": "FactorPageOverlays",
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
        "reactComponent": "FactorPageOverlays",
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
        "reactComponent": "FactorPageOverlays",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      }
    ],
    a11yRoles: {
      "header": "banner",
      "meta": "banner",
      "main": "region",
      "sidebar": "complementary",
    },
    responsiveBehavior: {
      "meta": "reflow",
      "sidebar": "collapsed",
    },
  },
  {
    route: "/research/factors",
    pagePattern: "catalog-screener",
    shellFamily: "catalog",
    prototypeSource: "prototype-backed",
    prototypeRef: "docs/designs/specs/prototypes/page-factor-list.html",
    requiredSlots: ["toolbar", "main", "detail"],
    requiredStates: ["loading", "empty", "error", "stale", "selected-factor", "filter-empty", "evidence-scope-missing", "factor-compare-open"],
    landing: {
      "reactRouteStatus": "implemented",
      "featureModule": "src/features/research",
      "contractStatus": "verified",
      "overlayStatus": "triggerable",
      "prototypeVerified": true,
      "reactParityVerified": true,
      "reactTestRefs": [
        "src/features/research/components/research-components.test.tsx",
        "src/features/research/components/factor-list-page-live.test.tsx"
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
        "reactComponent": "FactorCompareDrawer",
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
    requiredStates: ["loading", "empty", "error", "stale", "no-alerts", "has-critical", "daily-brief-stale", "pending-approvals", "priority-findings", "signal-evidence-open", "order-handoff-confirm", "workspace-settings-open", "decision-evidence-open"],
    sidebarCollapsible: true,
    landing: {
      "reactRouteStatus": "implemented",
      "featureModule": "src/features/home",
      "contractStatus": "verified",
      "overlayStatus": "triggerable",
      "prototypeVerified": true,
      "reactParityVerified": true,
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
          "action": "select-priority-item"
        },
        "prototypeSelector": "#overlay-signal-detail",
        "reactComponent": "HomeSignalEvidenceDrawer",
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
          "action": "prepare-order-handoff"
        },
        "prototypeSelector": "#overlay-order-confirm",
        "reactComponent": "HomeOrderHandoffDialog",
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
          "action": "open-workspace-settings"
        },
        "prototypeSelector": "#overlay-edit-workspace",
        "reactComponent": "HomeWorkspaceSettingsSheet",
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
          "action": "open-decision-evidence"
        },
        "prototypeSelector": "#overlay-ai-advice",
        "reactComponent": "HomeDecisionEvidenceDrawer",
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
    requiredSlots: ["header", "meta", "tabs", "main", "bottom"],
    requiredStates: ["loading", "empty", "error", "stale", "not-found", "invalid-id", "bars-empty", "snapshot-identity-missing", "experimental-disabled"],
    hasStatusBar: true,
    landing: {
      "reactRouteStatus": "implemented",
      "featureModule": "src/features/instruments",
      "contractStatus": "verified",
      "overlayStatus": "triggerable",
      "prototypeVerified": true,
      "reactParityVerified": true,
      "reactTestRefs": [
        "src/features/instruments/components/instrument-components.test.tsx",
        "src/features/instruments/components/info-level-annotations.test.tsx"
      ],
      "reactComponentRefs": [
        "InstrumentHubPage"
      ]
    },
    overlays: [
      {
        "id": "instrument-hub.chart-toolbar",
        "kind": "inline",
        "blocking": false,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "toggle"
        },
        "prototypeSelector": "#overlay-chart-toolbar",
        "reactComponent": "InstrumentPageOverlays",
        "closeBehavior": [
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
        "reactComponent": "InstrumentPageOverlays",
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
        "reactComponent": "InstrumentPageOverlays",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "instrument-hub.add-watchlist",
        "kind": "sheet",
        "blocking": false,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "bottom",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-add-watchlist",
        "reactComponent": "InstrumentPageOverlays",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "instrument-hub.send-research",
        "kind": "sheet",
        "blocking": false,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "bottom",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-send-research",
        "reactComponent": "InstrumentPageOverlays",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "instrument-hub.halt-detail",
        "kind": "modal",
        "blocking": false,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "meta",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-halt-detail",
        "reactComponent": "InstrumentPageOverlays",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      }
    ],
    a11yRoles: {
      "header": "banner",
      "meta": "banner",
      "tabs": "navigation",
      "main": "main",
      "bottom": "region",
    },
    responsiveBehavior: {
      "header": "reflow",
      "meta": "reflow",
      "tabs": "reflow",
      "bottom": "collapsed",
    },
  },
  {
    route: "/portfolio/manual",
    pagePattern: "analytical-overview",
    shellFamily: "analytical",
    prototypeSource: "prototype-backed",
    prototypeRef: "docs/designs/specs/prototypes/page-portfolio.html",
    requiredSlots: ["strip", "main", "activity", "analysis"],
    requiredStates: ["loading", "empty", "error", "stale", "ready", "account-unselected", "reconstruction-failed", "correction-required", "cloud-redacted", "confirmation-required"],
    landing: {
      "reactRouteStatus": "implemented",
      "featureModule": "src/features/portfolio",
      "contractStatus": "verified",
      "overlayStatus": "none",
      "prototypeVerified": false,
      "reactParityVerified": true,
      "reactTestRefs": [
        "src/features/portfolio/components/portfolio-components.test.tsx",
        "src/features/portfolio/components/manual-account-workspace.test.tsx"
      ],
      "reactComponentRefs": [
        "PortfolioPage",
        "ManualAccountWorkspace"
      ]
    },
    overlays: [],
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
    route: "/markets/industries",
    pagePattern: "catalog-screener",
    shellFamily: "catalog",
    prototypeSource: "prototype-backed",
    prototypeRef: "docs/designs/specs/prototypes/page-markets-screener.html",
    requiredSlots: ["toolbar", "main", "detail"],
    requiredStates: ["loading", "empty", "error", "stale", "snapshot-required", "ready", "degraded", "blocked", "industry-selected", "missing-inputs"],
    landing: {
      "reactRouteStatus": "implemented",
      "featureModule": "src/features/selection",
      "contractStatus": "verified",
      "overlayStatus": "none",
      "prototypeVerified": false,
      "reactParityVerified": false,
      "reactTestRefs": [
        "src/features/selection/components/industry-rotation-page.test.tsx"
      ],
      "reactComponentRefs": [
        "IndustryRotationPage"
      ]
    },
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
    route: "/markets/screener",
    pagePattern: "catalog-screener",
    shellFamily: "catalog",
    prototypeSource: "prototype-backed",
    prototypeRef: "docs/designs/specs/prototypes/page-markets-screener.html",
    requiredSlots: ["toolbar", "main", "detail"],
    requiredStates: ["loading", "empty", "error", "stale", "saved-run", "blocked-run", "candidate-selected", "exclusion-visible", "compare-ready", "input-invalid"],
    landing: {
      "reactRouteStatus": "implemented",
      "featureModule": "src/features/selection",
      "contractStatus": "verified",
      "overlayStatus": "implemented",
      "prototypeVerified": false,
      "reactParityVerified": false,
      "reactTestRefs": [
        "src/features/selection/components/selection-workspace-page.test.tsx"
      ],
      "reactComponentRefs": [
        "SelectionWorkspacePage"
      ]
    },
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
    route: "/portfolio/model",
    pagePattern: "analytical-overview",
    shellFamily: "analytical",
    prototypeSource: "prototype-backed",
    prototypeRef: "docs/designs/specs/prototypes/page-portfolio.html",
    requiredSlots: ["strip", "main", "activity", "analysis"],
    requiredStates: ["loading", "empty", "error", "stale", "ready", "review-required", "blocked", "partial", "solver-failed", "reconciliation-mismatch", "no-positions"],
    landing: {
      "reactRouteStatus": "implemented",
      "featureModule": "src/features/portfolio",
      "contractStatus": "verified",
      "overlayStatus": "none",
      "prototypeVerified": true,
      "reactParityVerified": true,
      "reactTestRefs": [
        "src/features/portfolio/components/portfolio-components.test.tsx",
        "src/features/portfolio/components/portfolio-construction-evidence.test.tsx",
        "src/features/portfolio/components/positions-summary.test.tsx"
      ],
      "reactComponentRefs": [
        "PortfolioPage",
        "PortfolioConstructionEvidence"
      ]
    },
    overlays: [],
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
    route: "/portfolio/paper",
    pagePattern: "analytical-overview",
    shellFamily: "analytical",
    prototypeSource: "prototype-backed",
    prototypeRef: "docs/designs/specs/prototypes/page-portfolio.html",
    requiredSlots: ["strip", "main", "activity", "analysis"],
    requiredStates: ["loading", "empty", "error", "stale", "ready", "workspace-unselected", "paused", "blocked", "reconciliation-mismatch", "recovered", "confirmation-required"],
    landing: {
      "reactRouteStatus": "implemented",
      "featureModule": "src/features/portfolio",
      "contractStatus": "verified",
      "overlayStatus": "none",
      "prototypeVerified": false,
      "reactParityVerified": true,
      "reactTestRefs": [
        "src/features/portfolio/components/portfolio-components.test.tsx",
        "src/features/portfolio/components/paper-account-workspace.test.tsx"
      ],
      "reactComponentRefs": [
        "PortfolioPage",
        "PaperAccountWorkspace"
      ]
    },
    overlays: [],
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
    route: "/portfolio",
    pagePattern: "analytical-overview",
    shellFamily: "analytical",
    prototypeSource: "prototype-backed",
    prototypeRef: "docs/designs/specs/prototypes/page-portfolio.html",
    requiredSlots: ["strip", "main", "activity", "analysis"],
    requiredStates: ["loading", "empty", "error", "stale", "ready", "identity-missing", "scenario-preview", "reconciliation-mismatch", "source-snapshot-mismatch"],
    landing: {
      "reactRouteStatus": "implemented",
      "featureModule": "src/features/portfolio",
      "contractStatus": "verified",
      "overlayStatus": "none",
      "prototypeVerified": true,
      "reactParityVerified": true,
      "reactTestRefs": [
        "src/features/portfolio/components/portfolio-components.test.tsx",
        "src/features/portfolio/components/portfolio-comparison-workspace.test.tsx"
      ],
      "reactComponentRefs": [
        "PortfolioPage",
        "PortfolioComparisonWorkspace"
      ]
    },
    overlays: [],
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
    route: "/portfolio/risk",
    pagePattern: "analytical-overview",
    shellFamily: "analytical",
    prototypeSource: "prototype-backed",
    prototypeRef: "docs/designs/specs/prototypes/page-risk-center.html",
    requiredSlots: ["strip", "main", "activity", "analysis"],
    requiredStates: ["loading", "empty", "error", "stale", "ready", "review-required", "blocked", "partial", "tail-risk-unavailable", "factor-risk-unavailable", "stress-scenario-unavailable", "reconciliation-mismatch", "provenance-missing", "breach-active", "shadow-opinion-unavailable"],
    hasStatusBar: true,
    landing: {
      "reactRouteStatus": "implemented",
      "featureModule": "src/features/portfolio",
      "contractStatus": "verified",
      "overlayStatus": "triggerable",
      "prototypeVerified": true,
      "reactParityVerified": true,
      "reactTestRefs": [
        "src/features/portfolio/components/risk-components.test.tsx",
        "src/features/portfolio/components/risk-breach-detail.test.tsx"
      ],
      "reactComponentRefs": [
        "RiskPage",
        "RiskMockWorkspace",
        "RiskStressDetailDrawer",
        "BreachDetailContent",
        "RiskRuleEditorSheet"
      ]
    },
    overlays: [
      {
        "id": "risk-center.stress-detail",
        "kind": "drawer",
        "blocking": false,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-stress-detail",
        "reactComponent": "RiskStressDetailDrawer",
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
    route: "/portfolio/transactions",
    pagePattern: "ledger-execution-console",
    shellFamily: "ops-console",
    prototypeSource: "prototype-backed",
    prototypeRef: "docs/designs/specs/prototypes/page-orders-ledger.html",
    requiredSlots: ["health", "main", "detail"],
    requiredStates: ["loading", "empty", "error", "stale", "selected-row", "order-active", "cancel-confirm", "retry-confirm", "batch-cancel", "partial-result"],
    hasStatusBar: true,
    landing: {
      "reactRouteStatus": "implemented",
      "featureModule": "src/features/portfolio",
      "contractStatus": "verified",
      "overlayStatus": "triggerable",
      "prototypeVerified": true,
      "reactParityVerified": true,
      "reactTestRefs": [
        "src/features/portfolio/components/orders-components.test.tsx"
      ],
      "reactComponentRefs": [
        "OrdersPage",
        "OrderDetailPanel"
      ]
    },
    overlays: [
      {
        "id": "orders-ledger.cancel-confirm",
        "kind": "modal",
        "blocking": true,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "detail",
          "action": "cancel-intent"
        },
        "prototypeSelector": "#overlay-cancel-confirm",
        "reactComponent": "OrderDetailPanel",
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
          "slot": "detail",
          "action": "retry-intent"
        },
        "prototypeSelector": "#overlay-retry-submit",
        "reactComponent": "OrderDetailPanel",
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
    route: "/research/agent",
    pagePattern: "studio-builder",
    shellFamily: "studio",
    prototypeSource: "prototype-backed",
    prototypeRef: "docs/designs/specs/prototypes/page-agent-console-v2.html",
    requiredSlots: ["shell", "header", "tabs", "source", "main", "inspector"],
    requiredStates: ["loading", "empty", "error", "stale", "disabled", "degraded", "running", "partial", "blocked", "waiting-approval", "approval-expired", "guardrail-blocked", "cancelled", "failed", "completed", "reconnecting"],
    hasStatusBar: true,
    landing: {
      "reactRouteStatus": "implemented",
      "featureModule": "src/features/agent",
      "contractStatus": "verified",
      "overlayStatus": "triggerable",
      "prototypeVerified": true,
      "reactParityVerified": true,
      "reactTestRefs": [
        "src/features/agent/components/agent-console-page.test.tsx",
        "src/features/agent/components/agent-overlays.test.tsx",
        "src/features/agent/components/agent-author-preview.test.tsx"
      ],
      "reactComponentRefs": [
        "AgentConsolePage"
      ]
    },
    overlays: [
      {
        "id": "agent-console.run-create",
        "kind": "sheet",
        "blocking": false,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-run-create",
        "reactComponent": "AgentRunCreateSheet",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "agent-console.run-cancel",
        "kind": "modal",
        "blocking": true,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-run-cancel",
        "reactComponent": "AgentRunCancelDialog",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "agent-console.approval-exact-action",
        "kind": "modal",
        "blocking": true,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-approval-exact-action",
        "reactComponent": "AgentApprovalExactActionDialog",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "agent-console.evidence-detail",
        "kind": "drawer",
        "blocking": false,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-evidence-detail",
        "reactComponent": "AgentEvidenceDetailDrawer",
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
        "reactComponent": "AgentArtifactPreviewDrawer",
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
        "reactComponent": "AgentGuardrailDetailDrawer",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "agent-console.campaign-draft",
        "kind": "sheet",
        "blocking": false,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "create-campaign"
        },
        "prototypeSelector": "#overlay-campaign-draft",
        "reactComponent": "AgentCampaignDraftSheet",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "agent-console.campaign-approval",
        "kind": "modal",
        "blocking": true,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "approve-campaign"
        },
        "prototypeSelector": "#overlay-campaign-approval",
        "reactComponent": "AgentCampaignApprovalDialog",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "agent-console.campaign-cancel",
        "kind": "modal",
        "blocking": true,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "cancel-campaign"
        },
        "prototypeSelector": "#overlay-campaign-cancel",
        "reactComponent": "AgentCampaignCancelDialog",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      }
    ],
    a11yRoles: {
      "shell": "region",
      "header": "banner",
      "tabs": "tablist",
      "source": "complementary",
      "main": "main",
      "inspector": "complementary",
    },
    responsiveBehavior: {
      "shell": "reflow",
      "header": "collapsed",
      "tabs": "reflow",
      "source": "collapsed",
      "main": "reflow",
      "inspector": "overlay",
    },
  },
  {
    route: "/research",
    pagePattern: "analytical-overview",
    shellFamily: "analytical",
    prototypeSource: "prototype-backed",
    prototypeRef: "docs/designs/specs/prototypes/page-research.html",
    requiredSlots: ["strip", "main", "activity", "analysis"],
    requiredStates: ["loading", "empty", "error", "stale", "no-runs", "factor-catalog-empty", "evidence-scope-missing", "run-detail-open", "review-action-open"],
    landing: {
      "reactRouteStatus": "implemented",
      "featureModule": "src/features/research",
      "contractStatus": "verified",
      "overlayStatus": "triggerable",
      "prototypeVerified": true,
      "reactParityVerified": true,
      "reactTestRefs": [
        "src/features/research/components/info-level-annotations.test.tsx",
        "src/features/research/components/research-components.test.tsx",
        "src/features/research/components/research-page-workspace.test.tsx",
        "src/features/research/live-boundary.test.tsx"
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
        "reactComponent": "ResearchOverlays",
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
        "reactComponent": "ResearchOverlays",
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
        "reactComponent": "ResearchOverlays",
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
        "reactComponent": "ResearchOverlays",
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
        "reactComponent": "ResearchOverlays",
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
    prototypeRef: "docs/designs/specs/prototypes/page-strategies-detail.html",
    requiredSlots: ["header", "meta", "tabs", "main", "bottom"],
    requiredStates: ["loading", "empty", "error", "stale", "selected-decision-tab", "selected-evidence-tab", "selected-lineage-tab", "selected-audit-tab", "packet-unavailable", "partial-version-error", "partial-diff-error", "hard-gate-blocked", "review-pending", "approved-awaiting-publish", "published", "rejected"],
    landing: {
      "reactRouteStatus": "implemented",
      "featureModule": "src/features/research",
      "contractStatus": "verified",
      "overlayStatus": "triggerable",
      "prototypeVerified": true,
      "reactParityVerified": true,
      "reactTestRefs": [
        "src/features/research/components/review-detail-page.test.tsx",
        "src/features/strategy/components/review-decision-panel.test.tsx"
      ],
      "reactComponentRefs": [
        "ReviewDetailPage",
        "ReviewDecisionPanel"
      ]
    },
    overlays: [
      {
        "id": "review-detail.governance-confirmation",
        "kind": "sheet",
        "blocking": true,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-version-rollback",
        "reactComponent": "DecisionDialog|PublishDialog",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      }
    ],
    a11yRoles: {
      "header": "banner",
      "meta": "complementary",
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
    route: "/research/reviews",
    pagePattern: "catalog-screener",
    shellFamily: "catalog",
    prototypeSource: "prototype-backed",
    prototypeRef: "docs/designs/specs/prototypes/page-experiment-list.html",
    requiredSlots: ["toolbar", "main", "detail"],
    requiredStates: ["loading", "empty", "error", "stale", "selected-review", "filtered-results", "filtered-empty", "packet-missing", "pending-review", "approved-awaiting-publish"],
    landing: {
      "reactRouteStatus": "implemented",
      "featureModule": "src/features/research",
      "contractStatus": "verified",
      "overlayStatus": "none",
      "prototypeVerified": true,
      "reactParityVerified": true,
      "reactTestRefs": [
        "src/features/research/components/review-queue-page.test.tsx"
      ],
      "reactComponentRefs": [
        "ReviewQueuePage"
      ]
    },
    overlays: [],
    a11yRoles: {
      "toolbar": "toolbar",
      "main": "main",
      "detail": "complementary",
    },
    responsiveBehavior: {
      "toolbar": "reflow",
      "detail": "unchanged",
    },
  },
  {
    route: "/portfolio/review",
    pagePattern: "queue-ops-console",
    shellFamily: "ops-console",
    prototypeSource: "prototype-backed",
    prototypeRef: "docs/designs/specs/prototypes/page-signals-inbox.html",
    requiredSlots: ["health", "main", "detail"],
    requiredStates: ["loading", "empty", "error", "stale", "selected-row", "sheet-open", "ai-review", "risk-pass", "risk-warn", "risk-block", "evidence-open", "manual-fill-open"],
    hasStatusBar: true,
    landing: {
      "reactRouteStatus": "implemented",
      "featureModule": "src/features/portfolio",
      "contractStatus": "verified",
      "overlayStatus": "triggerable",
      "prototypeVerified": true,
      "reactParityVerified": true,
      "reactTestRefs": [
        "src/features/portfolio/components/signals-components.test.tsx"
      ],
      "reactComponentRefs": [
        "SignalsPage",
        "SignalDetailPanel"
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
        "reactComponent": "SignalOrderPreviewDialog",
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
        "reactComponent": "SignalEvidenceDialog",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "signals.batch-review",
        "kind": "modal",
        "blocking": true,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-batch-review"
        },
        "prototypeSelector": "#overlay-batch-confirm",
        "reactComponent": "SignalsBatchReviewDialog",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "signals.order-preview",
        "kind": "modal",
        "blocking": true,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "detail",
          "action": "review-order-intent"
        },
        "prototypeSelector": "#overlay-signal-confirm-to-order",
        "reactComponent": "SignalOrderPreviewDialog",
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
    requiredSlots: ["header", "meta", "tabs", "main", "bottom"],
    requiredStates: ["loading", "empty", "error", "stale", "selected-overview-tab", "selected-version-tab", "selected-factor-tab", "performance-evidence-missing", "backtest-planning-handoff", "copy-draft-open", "deprecation-command-open", "rollback-governance-open"],
    landing: {
      "reactRouteStatus": "implemented",
      "featureModule": "src/features/strategy",
      "contractStatus": "verified",
      "overlayStatus": "triggerable",
      "prototypeVerified": true,
      "reactParityVerified": true,
      "reactTestRefs": [
        "src/features/strategy/components/info-level-annotations.test.tsx",
        "src/features/strategy/components/strategy-detail-components.test.tsx",
        "src/features/strategy/components/strategy-detail-page-workspace.test.tsx",
        "src/features/strategy/components/strategy-version-detail.test.tsx"
      ],
      "reactComponentRefs": [
        "StrategyDetailPage"
      ]
    },
    overlays: [
      {
        "id": "strategies-detail.deprecate-strategy",
        "kind": "modal",
        "blocking": true,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-delete-strategy",
        "reactComponent": "StrategyDetailOverlays",
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
        "reactComponent": "StrategyDetailOverlays",
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
        "reactComponent": "StrategyDetailOverlays",
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
        "reactComponent": "StrategyDetailOverlays",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      }
    ],
    a11yRoles: {
      "header": "banner",
      "meta": "complementary",
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
    requiredStates: ["loading", "empty", "error", "stale", "selected-strategy", "filter-empty", "performance-evidence-missing", "new-draft-open", "clone-draft-open", "deprecation-governance-open"],
    landing: {
      "reactRouteStatus": "implemented",
      "featureModule": "src/features/strategy",
      "contractStatus": "verified",
      "overlayStatus": "triggerable",
      "prototypeVerified": true,
      "reactParityVerified": true,
      "reactTestRefs": [
        "src/features/strategy/components/strategy-list-page-live.test.tsx"
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
        "reactComponent": "StrategyListOverlays",
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
        "reactComponent": "StrategyListOverlays",
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
    requiredSlots: ["header", "modes", "source", "main", "inspector", "logs"],
    requiredStates: ["loading", "empty", "error", "stale", "selected-form-mode", "selected-pipeline-mode", "working-copy-dirty", "validation-ready", "validation-stale", "validation-error", "save-pending", "save-success", "dry-run-planning", "backtest-planning", "factor-preview-live", "deprecation-command-open"],
    hasStatusBar: true,
    landing: {
      "reactRouteStatus": "implemented",
      "featureModule": "src/features/strategy",
      "contractStatus": "verified",
      "overlayStatus": "triggerable",
      "prototypeVerified": true,
      "reactParityVerified": true,
      "reactTestRefs": [
        "src/features/strategy/components/info-level-annotations.test.tsx",
        "src/features/strategy/components/strategy-components.test.tsx",
        "src/features/strategy/components/strategy-page-workspace.test.tsx",
        "src/features/strategy/components/studio-mode-bar.test.tsx"
      ],
      "reactComponentRefs": [
        "StrategyPage"
      ]
    },
    overlays: [
      {
        "id": "strategy-studio.deprecate-strategy",
        "kind": "modal",
        "blocking": true,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "header",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-delete-strategy",
        "reactComponent": "StrategyStudioOverlays",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "strategy-studio.save-strategy",
        "kind": "modal",
        "blocking": true,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "header",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-save-strategy",
        "reactComponent": "StrategyStudioOverlays",
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
          "slot": "header",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-validation-toast",
        "reactComponent": "StrategyPage",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "strategy-studio.backtest-config",
        "kind": "sheet",
        "blocking": false,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "header",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-backtest-config",
        "reactComponent": "StrategyStudioOverlays",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "strategy-studio.factor-preview",
        "kind": "sheet",
        "blocking": false,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "source",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-factor-preview",
        "reactComponent": "StrategyStudioOverlays",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      }
    ],
    a11yRoles: {
      "header": "banner",
      "modes": "navigation",
      "source": "complementary",
      "main": "main",
      "inspector": "complementary",
      "logs": "log",
    },
    responsiveBehavior: {
      "modes": "unchanged",
      "source": "unchanged",
      "inspector": "unchanged",
      "logs": "unchanged",
    },
  },
  {
    route: "/system/agent",
    pagePattern: "studio-builder",
    shellFamily: "studio",
    prototypeSource: "prototype-backed",
    prototypeRef: "docs/designs/specs/prototypes/page-agent-console-v2.html",
    requiredSlots: ["shell", "header", "tabs", "source", "main", "inspector"],
    requiredStates: ["loading", "empty", "error", "stale", "disabled", "degraded", "running", "partial", "blocked", "waiting-approval", "approval-expired", "guardrail-blocked", "cancelled", "failed", "completed", "reconnecting"],
    hasStatusBar: true,
    landing: {
      "reactRouteStatus": "implemented",
      "featureModule": "src/features/system",
      "contractStatus": "verified",
      "overlayStatus": "triggerable",
      "prototypeVerified": true,
      "reactParityVerified": true,
      "reactTestRefs": [
        "src/features/agent/components/agent-console-page.test.tsx",
        "src/features/agent/components/agent-overlays.test.tsx",
        "src/workflows/system-agent-ops/system-agent-ops-page.test.tsx"
      ],
      "reactComponentRefs": [
        "SystemAgentOpsPage"
      ]
    },
    overlays: [
      {
        "id": "agent-console.run-create",
        "kind": "sheet",
        "blocking": false,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-run-create",
        "reactComponent": "AgentRunCreateSheet",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "agent-console.run-cancel",
        "kind": "modal",
        "blocking": true,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-run-cancel",
        "reactComponent": "AgentRunCancelDialog",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "agent-console.approval-exact-action",
        "kind": "modal",
        "blocking": true,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-approval-exact-action",
        "reactComponent": "AgentApprovalExactActionDialog",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "agent-console.evidence-detail",
        "kind": "drawer",
        "blocking": false,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-evidence-detail",
        "reactComponent": "AgentEvidenceDetailDrawer",
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
        "reactComponent": "AgentArtifactPreviewDrawer",
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
        "reactComponent": "AgentGuardrailDetailDrawer",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "agent-console.campaign-draft",
        "kind": "sheet",
        "blocking": false,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "create-campaign"
        },
        "prototypeSelector": "#overlay-campaign-draft",
        "reactComponent": "AgentCampaignDraftSheet",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "agent-console.campaign-approval",
        "kind": "modal",
        "blocking": true,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "approve-campaign"
        },
        "prototypeSelector": "#overlay-campaign-approval",
        "reactComponent": "AgentCampaignApprovalDialog",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "agent-console.campaign-cancel",
        "kind": "modal",
        "blocking": true,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "cancel-campaign"
        },
        "prototypeSelector": "#overlay-campaign-cancel",
        "reactComponent": "AgentCampaignCancelDialog",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      }
    ],
    a11yRoles: {
      "shell": "region",
      "header": "banner",
      "tabs": "tablist",
      "source": "complementary",
      "main": "main",
      "inspector": "complementary",
    },
    responsiveBehavior: {
      "shell": "reflow",
      "header": "collapsed",
      "tabs": "reflow",
      "source": "collapsed",
      "main": "reflow",
      "inspector": "overlay",
    },
  },
  {
    route: "/system/audit",
    pagePattern: "queue-ops-console",
    shellFamily: "ops-console",
    prototypeSource: "prototype-backed",
    prototypeRef: "docs/designs/specs/prototypes/page-platform.html",
    requiredSlots: ["health", "main", "detail"],
    requiredStates: ["loading", "empty", "error", "stale", "catalog-empty", "pipeline-running", "source-degraded", "fallback-active", "promotion-blocked", "approval-expired", "partial-unavailable", "remediation-empty"],
    hasStatusBar: true,
    landing: {
      "reactRouteStatus": "implemented",
      "featureModule": "src/features/system",
      "contractStatus": "verified",
      "overlayStatus": "triggerable",
      "prototypeVerified": false,
      "reactParityVerified": true,
      "reactTestRefs": [
        "src/features/system/components/system-components.test.tsx",
        "src/features/system/components/info-level-annotations.test.tsx",
        "src/features/system/hooks/system-hooks.test.tsx",
        "src/features/system/api/system-overview.test.ts"
      ],
      "reactComponentRefs": [
        "SystemPage"
      ]
    },
    overlays: [
      {
        "id": "system.pipeline-rerun",
        "kind": "modal",
        "blocking": true,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-pipeline-rerun",
        "reactComponent": "SystemOverlays",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "system.alert-handle",
        "kind": "alert-dialog",
        "blocking": true,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "detail",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-alert-handle",
        "reactComponent": "SystemOverlays",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "system.task-detail",
        "kind": "drawer",
        "blocking": false,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-task-detail",
        "reactComponent": "SystemOverlays",
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
      "health": "unchanged",
      "main": "unchanged",
      "detail": "unchanged",
    },
  },
  {
    route: "/system/jobs",
    pagePattern: "queue-ops-console",
    shellFamily: "ops-console",
    prototypeSource: "prototype-backed",
    prototypeRef: "docs/designs/specs/prototypes/page-platform.html",
    requiredSlots: ["health", "main", "detail"],
    requiredStates: ["loading", "empty", "error", "stale", "catalog-empty", "pipeline-running", "source-degraded", "fallback-active", "promotion-blocked", "approval-expired", "partial-unavailable", "remediation-empty"],
    hasStatusBar: true,
    landing: {
      "reactRouteStatus": "implemented",
      "featureModule": "src/features/system",
      "contractStatus": "verified",
      "overlayStatus": "triggerable",
      "prototypeVerified": false,
      "reactParityVerified": true,
      "reactTestRefs": [
        "src/features/system/components/system-components.test.tsx",
        "src/features/system/components/info-level-annotations.test.tsx",
        "src/features/system/hooks/system-hooks.test.tsx",
        "src/features/system/api/system-overview.test.ts"
      ],
      "reactComponentRefs": [
        "SystemPage"
      ]
    },
    overlays: [
      {
        "id": "system.pipeline-rerun",
        "kind": "modal",
        "blocking": true,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-pipeline-rerun",
        "reactComponent": "SystemOverlays",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "system.alert-handle",
        "kind": "alert-dialog",
        "blocking": true,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "detail",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-alert-handle",
        "reactComponent": "SystemOverlays",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "system.task-detail",
        "kind": "drawer",
        "blocking": false,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-task-detail",
        "reactComponent": "SystemOverlays",
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
      "health": "unchanged",
      "main": "unchanged",
      "detail": "unchanged",
    },
  },
  {
    route: "/system/settings",
    pagePattern: "config-integration-console",
    shellFamily: "ops-console",
    prototypeSource: "prototype-backed",
    prototypeRef: "docs/designs/specs/prototypes/page-platform-settings.html",
    requiredSlots: ["health", "main", "detail"],
    requiredStates: ["loading", "empty", "error", "stale", "catalog-empty", "runtime-unavailable", "agent-degraded", "partial-unavailable", "read-only-boundary"],
    landing: {
      "reactRouteStatus": "implemented",
      "featureModule": "src/features/system",
      "contractStatus": "verified",
      "overlayStatus": "triggerable",
      "prototypeVerified": true,
      "reactParityVerified": false,
      "reactTestRefs": [
        "src/features/system/components/system-components.test.tsx",
        "src/features/system/hooks/system-hooks.test.tsx",
        "src/features/system/api/system-settings.test.ts"
      ],
      "reactComponentRefs": [
        "SystemSettingsPage"
      ]
    },
    overlays: [
      {
        "id": "system-settings.datasource-test",
        "kind": "sheet",
        "blocking": false,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-datasource-test",
        "reactComponent": "SystemSettingsOverlays",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "system-settings.save-config",
        "kind": "modal",
        "blocking": true,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-save-config",
        "reactComponent": "SystemSettingsOverlays",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "system-settings.reset-config",
        "kind": "alert-dialog",
        "blocking": true,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "detail",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-reset-config",
        "reactComponent": "SystemSettingsOverlays",
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
      "health": "unchanged",
      "main": "unchanged",
      "detail": "unchanged",
    },
  },
  {
    route: "/system",
    pagePattern: "queue-ops-console",
    shellFamily: "ops-console",
    prototypeSource: "prototype-backed",
    prototypeRef: "docs/designs/specs/prototypes/page-platform.html",
    requiredSlots: ["health", "main", "detail"],
    requiredStates: ["loading", "empty", "error", "stale", "catalog-empty", "pipeline-running", "source-degraded", "fallback-active", "promotion-blocked", "approval-expired", "partial-unavailable", "remediation-empty"],
    hasStatusBar: true,
    landing: {
      "reactRouteStatus": "implemented",
      "featureModule": "src/features/system",
      "contractStatus": "verified",
      "overlayStatus": "triggerable",
      "prototypeVerified": true,
      "reactParityVerified": true,
      "reactTestRefs": [
        "src/features/system/components/system-components.test.tsx",
        "src/features/system/components/info-level-annotations.test.tsx",
        "src/features/system/hooks/system-hooks.test.tsx",
        "src/features/system/api/system-overview.test.ts"
      ],
      "reactComponentRefs": [
        "SystemPage"
      ]
    },
    overlays: [
      {
        "id": "system.pipeline-rerun",
        "kind": "modal",
        "blocking": true,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-pipeline-rerun",
        "reactComponent": "SystemOverlays",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "system.alert-handle",
        "kind": "alert-dialog",
        "blocking": true,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "detail",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-alert-handle",
        "reactComponent": "SystemOverlays",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "system.task-detail",
        "kind": "drawer",
        "blocking": false,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "main",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-task-detail",
        "reactComponent": "SystemOverlays",
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
      "health": "unchanged",
      "main": "unchanged",
      "detail": "unchanged",
    },
  },
  {
    route: "/research/universes",
    pagePattern: "catalog-screener",
    shellFamily: "catalog",
    prototypeSource: "prototype-backed",
    prototypeRef: "docs/designs/specs/prototypes/page-universe-list.html",
    requiredSlots: ["toolbar", "main", "detail"],
    requiredStates: ["loading", "empty", "error", "stale", "selected-universe", "filtered-results", "filtered-empty", "preset-definition", "custom-definition", "membership-asof-unbound", "membership-loading", "membership-empty", "membership-unavailable", "create-failed", "update-failed", "delete-failed"],
    landing: {
      "reactRouteStatus": "implemented",
      "featureModule": "src/features/research",
      "contractStatus": "verified",
      "overlayStatus": "triggerable",
      "prototypeVerified": true,
      "reactParityVerified": true,
      "reactTestRefs": [
        "src/features/research/components/universe-list-page.test.tsx",
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
          "slot": "detail",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-universe-edit",
        "reactComponent": "CreateUniverseSheet|EditUniverseSheet",
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
          "slot": "detail",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-universe-delete",
        "reactComponent": "DeleteUniverseDialog",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      }
    ],
    a11yRoles: {
      "toolbar": "toolbar",
      "main": "main",
      "detail": "complementary",
    },
    responsiveBehavior: {
      "toolbar": "reflow",
      "detail": "unchanged",
    },
  },
  {
    route: "/markets/watchlist",
    pagePattern: "catalog-screener",
    shellFamily: "catalog",
    prototypeSource: "prototype-backed",
    prototypeRef: "docs/designs/specs/prototypes/page-watchlist.html",
    requiredSlots: ["toolbar", "main", "detail"],
    requiredStates: ["loading", "empty", "error", "stale", "no-symbols", "invalid-id", "instrument-not-found", "local-only"],
    landing: {
      "reactRouteStatus": "implemented",
      "featureModule": "src/features/markets",
      "contractStatus": "verified",
      "overlayStatus": "triggerable",
      "prototypeVerified": true,
      "reactParityVerified": true,
      "reactTestRefs": [
        "src/features/markets/components/markets-components.test.tsx",
        "src/features/markets/components/info-level-annotations.test.tsx"
      ],
      "reactComponentRefs": [
        "WatchlistPage"
      ]
    },
    overlays: [
      {
        "id": "watchlist.add-instrument",
        "kind": "drawer",
        "blocking": false,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "toolbar",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-add-instrument",
        "reactComponent": "WatchlistOverlay",
        "closeBehavior": [
          "escape",
          "outside-click",
          "primary-action"
        ]
      },
      {
        "id": "watchlist.bulk-delete",
        "kind": "alert-dialog",
        "blocking": true,
        "requiredInDefaultFlow": true,
        "trigger": {
          "slot": "toolbar",
          "action": "open-overlay"
        },
        "prototypeSelector": "#overlay-bulk-delete",
        "reactComponent": "WatchlistOverlay",
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
