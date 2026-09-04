// AUTO-GENERATED — do not edit manually
// Run: bun run generate-contracts

export const PROTOTYPE_NORMALIZE_CSS = `
  .proto-nav { display: none !important; }
  #default-view {
    height: 100vh !important;
    min-height: 100vh !important;
    overflow: hidden !important;
  }
  #default-view > [class*="shell"],
  #default-view > .ai-shell,
  #default-view > .intel-shell,
  #default-view > .risk-shell {
    height: 100vh !important;
    min-height: 0 !important;
    flex: 0 0 auto !important;
  }
  #default-view > .shell-radar {
    align-items: stretch !important;
    overflow: hidden !important;
  }
  #default-view > .shell-radar > .shell-body {
    height: 100% !important;
    min-height: 0 !important;
    overflow: hidden !important;
  }
  #default-view > .shell-radar > .shell-body > .shell-header,
  #default-view > .shell-radar > .shell-body > .context-bar,
  #default-view > .shell-radar > .shell-body > .scope-strip,
  #default-view > .shell-radar > .shell-body > .status-bar {
    flex-shrink: 0 !important;
  }
  #default-view > .shell-radar > .shell-body > .shell-workspace {
    flex: 1 1 auto !important;
    min-height: 0 !important;
    overflow: hidden !important;
  }
  #default-view > .shell-radar .shell-workspace > .main-content,
  #default-view > .shell-radar .shell-workspace > .right-rail {
    height: 100% !important;
    min-height: 0 !important;
    overflow: auto !important;
  }
  #default-view > .shell-hub {
    padding-bottom: 0 !important;
  }
  #default-view > .shell-hub .tab-panel[aria-hidden="false"] {
    grid-area: main !important;
    height: 100% !important;
    min-height: 0 !important;
  }
  #default-view > .shell-studio > .studio-logs {
    height: 132px !important;
    min-height: 132px !important;
  }
  #default-view:has(> .shell-studio) > .status-bar {
    width: calc(100% - 56px) !important;
    margin-left: 56px !important;
  }
  @media (max-width: 1280px) {
    #default-view > .shell-studio {
      --prototype-studio-source-width: 200px !important;
      --prototype-studio-inspector-width: 280px !important;
    }
  }
  #default-view > [class*="shell"] > .danger-confirmation-summary {
    display: none !important;
  }
  #default-view > .status-bar {
    height: 24px !important;
    flex: 0 0 auto !important;
  }
  #default-view:has(> .status-bar) > [class*="shell"],
  #default-view:has(> .status-bar) > .ai-shell,
  #default-view:has(> .status-bar) > .intel-shell,
  #default-view:has(> .status-bar) > .risk-shell {
    height: calc(100vh - 24px) !important;
  }
`;

const PROTOTYPE_APP_TARGETS = {
  rail: ".shell-rail",
  header: ".shell-header, .studio-header, .object-header",
};

const PROTOTYPE_WITH_STATUS_BAR = {
  status: ".status-bar",
};

const REACT_NO_STATUS_BAR = {
  status: undefined,
};

export const VISUAL_AUDIT_PAGES = [
  {
    route: "/markets/a-shares",
    name: "a-shares",
    prototype: "page-a-shares.html",
    prototypeTargets: {
      'shell': "#default-view > [class*='shell']",
      'rail': ".shell-rail",
      'header': ".shell-header",
      'strip': ".scope-strip",
      'main': ".main-content",
      'activity': ".right-rail",
    },
    reactTargets: {
      'shell': "#root > div",
      'rail': "nav[aria-label='主导航']",
      'header': "header",
      'strip': "[data-slot='strip']",
      'main': "[data-slot='main']",
      'activity': "[data-slot='activity']",
    },
    targetThresholds: {
      "shell": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "rail": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "header": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "strip": {
        "x": 4,
        "y": 36,
        "widthRatio": 0.01,
        "heightRatio": 0.5
      },
      "main": {
        "x": 4,
        "y": 20,
        "widthRatio": 0.01,
        "heightRatio": 0.56
      },
      "activity": {
        "x": 8,
        "y": 20,
        "widthRatio": 0.03,
        "heightRatio": 0.56
      }
    },
    visualThresholds: {
      "consoleErrors": 0,
      "pageErrors": 0,
      "missingSelectors": 0,
      "targetMismatch": 0,
      "pixelDiffRatio": 0.18
    },
  },
  {
    route: "/system/approvals",
    name: "agent-approvals",
    prototype: "page-agent-console-v2.html",
    prototypeTargets: {
      'shell': ".agent-shell",
      'rail': ".shell-rail",
      'header': ".agent-header",
      'tabs': ".agent-tabs",
      'source': ".list-panel",
      'main': ".main-panel",
      'inspector': ".inspector",
      'status': ".status-bar",
    },
    reactTargets: {
      'shell': "[data-slot='app-shell']",
      'rail': "nav[aria-label='主导航']",
      'header': "[data-slot='header']",
      'tabs': "[data-slot='task-toolbar']",
      'source': "[data-slot='source']",
      'main': "[data-slot='main']",
      'inspector': "[data-slot='inspector']",
      'status': "[data-slot='status-bar']",
    },
    targetThresholds: {
      "shell": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "rail": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "header": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "tabs": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "source": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "main": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "inspector": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "status": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      }
    },
    visualThresholds: {
      "consoleErrors": 0,
      "pageErrors": 0,
      "missingSelectors": 0,
      "targetMismatch": 0,
      "pixelDiffRatio": 0.05
    },
  },
  {
    route: "/research/backtests",
    name: "backtest-list",
    prototype: "page-backtest-list.html",
    prototypeTargets: {
      'shell': "#default-view > [class*='shell']",
      'rail': ".shell-rail",
      'header': ".shell-header",
      'toolbar': ".filter-toolbar",
      'main': ".catalog-table",
      'detail': ".catalog-detail",
    },
    reactTargets: {
      'shell': "#root > div",
      'rail': "nav[aria-label='主导航']",
      'header': "header",
      'toolbar': "[data-slot='toolbar']",
      'main': "[data-slot='main']",
      'detail': "[data-slot='detail']",
    },
    targetThresholds: {
      "shell": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "rail": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "header": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "toolbar": {
        "x": 6,
        "y": 44,
        "widthRatio": 0.03,
        "heightRatio": 0.55
      },
      "main": {
        "x": 10,
        "y": 22,
        "widthRatio": 0.08,
        "heightRatio": 0.12
      },
      "detail": {
        "x": 22,
        "y": 60,
        "widthRatio": 0.2,
        "heightRatio": 0.16
      }
    },
    visualThresholds: {
      "consoleErrors": 0,
      "pageErrors": 0,
      "missingSelectors": 0,
      "targetMismatch": 0,
      "pixelDiffRatio": 0.075
    },
  },
  {
    route: "/research/backtests/$id",
    resolvedRoute: "/research/backtests/bt-001",
    name: "backtest-result",
    prototype: "page-backtest-result.html",
    prototypeTargets: {
      'shell': "#default-view > [class*='shell']",
      'rail': ".shell-rail",
      'header': ".shell-header",
      'meta': ".hub-meta",
      'tabs': ".hub-tabs",
      'main': "[data-contract-slot='main']",
      'bottom': ".hub-bottom",
    },
    reactTargets: {
      'shell': "#root > div",
      'rail': "nav[aria-label='主导航']",
      'header': "[data-slot='header']",
      'meta': "[data-testid='backtest-detail-identity']",
      'tabs': "[data-testid='backtest-detail-tabs']",
      'main': "[data-slot='main']",
      'bottom': "[data-testid='backtest-detail-bottom']",
    },
    targetThresholds: {
      "shell": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "rail": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "header": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.11
      },
      "meta": {
        "x": 4,
        "y": 12,
        "widthRatio": 0.03,
        "heightRatio": 0.08
      },
      "tabs": {
        "x": 4,
        "y": 68,
        "widthRatio": 0.03,
        "heightRatio": 0.08
      },
      "main": {
        "x": 4,
        "y": 68,
        "widthRatio": 0.03,
        "heightRatio": 0.2
      },
      "bottom": {
        "x": 4,
        "y": 12,
        "widthRatio": 0.03,
        "heightRatio": 0.12
      }
    },
    visualThresholds: {
      "consoleErrors": 0,
      "pageErrors": 0,
      "missingSelectors": 0,
      "targetMismatch": 0,
      "pixelDiffRatio": 0.075
    },
  },
  {
    route: "/markets",
    name: "cross-market",
    prototype: "page-cross-market.html",
    prototypeTargets: {
      'shell': "#default-view > [class*='shell']",
      'rail': ".shell-rail",
      'header': ".shell-header",
      'context-bar': ".context-bar",
      'scope-strip': ".scope-strip",
      'main': ".main-content",
      'right-rail': ".right-rail",
      'status': ".status-bar",
    },
    reactTargets: {
      'shell': "#root > div",
      'rail': "nav[aria-label='主导航']",
      'header': "header",
      'context-bar': "[data-slot='context-bar']",
      'scope-strip': "[data-slot='scope-strip']",
      'main': "[data-slot='main']",
      'right-rail': "[data-slot='right-rail']",
      'status': "[data-slot='status-bar']",
    },
    targetThresholds: {
      "shell": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "rail": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "header": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "context-bar": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.01,
        "heightRatio": 1
      },
      "scope-strip": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.01,
        "heightRatio": 1
      },
      "main": {
        "x": 4,
        "y": 70,
        "widthRatio": 0.01,
        "heightRatio": 0.74
      },
      "right-rail": {
        "x": 8,
        "y": 20,
        "widthRatio": 0.03,
        "heightRatio": 0.82
      },
      "status": {
        "x": 4,
        "y": 530,
        "widthRatio": 0.01,
        "heightRatio": 0.05
      }
    },
    visualThresholds: {
      "consoleErrors": 0,
      "pageErrors": 0,
      "missingSelectors": 0,
      "targetMismatch": 0,
      "pixelDiffRatio": 0.05
    },
  },
  {
    route: "/research/experiments/new",
    name: "experiment-create",
    prototype: "page-strategy-studio.html",
    prototypeTargets: {
      'shell': "#default-view > [class*='shell']",
      'rail': ".shell-rail",
      'header': ".studio-header",
      'modes': ".studio-mode-bar",
      'source': ".studio-sources",
      'main': ".studio-main",
      'inspector': ".studio-inspector",
      'logs': ".studio-logs",
      'status': ".status-bar",
    },
    reactTargets: {
      'shell': "#root > div",
      'rail': "nav[aria-label='主导航']",
      'header': "[data-slot='header']",
      'modes': "[data-slot='modes']",
      'source': "[data-slot='source']",
      'main': "[data-slot='main']",
      'inspector': "[data-slot='inspector']",
      'logs': "[data-slot='logs']",
      'status': "[data-slot='status-bar']",
    },
    targetThresholds: {
      "shell": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "rail": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "header": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.11
      },
      "modes": {
        "x": 4,
        "y": 6,
        "widthRatio": 0.03,
        "heightRatio": 0.08
      },
      "source": {
        "x": 8,
        "y": 8,
        "widthRatio": 0.3,
        "heightRatio": 0.08
      },
      "main": {
        "x": 8,
        "y": 8,
        "widthRatio": 0.08,
        "heightRatio": 0.08
      },
      "inspector": {
        "x": 8,
        "y": 8,
        "widthRatio": 0.12,
        "heightRatio": 0.08
      },
      "logs": {
        "x": 8,
        "y": 18,
        "widthRatio": 0.03,
        "heightRatio": 0.55
      },
      "status": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      }
    },
    visualThresholds: {
      "consoleErrors": 0,
      "pageErrors": 0,
      "missingSelectors": 0,
      "targetMismatch": 0,
      "pixelDiffRatio": 0.075
    },
  },
  {
    route: "/research/experiments/$id",
    name: "experiment-detail",
    prototype: "page-strategies-detail.html",
    prototypeTargets: {
      'shell': "#default-view > [class*='shell']",
      'rail': ".shell-rail",
      'header': ".shell-header",
      'meta': ".hub-meta",
      'tabs': ".hub-tabs",
      'main': "[data-contract-slot='main']",
      'bottom': ".hub-bottom",
    },
    reactTargets: {
      'shell': "#root > div",
      'rail': "nav[aria-label='主导航']",
      'header': "[data-slot='header']",
      'meta': "[data-testid='experiment-detail-meta']",
      'tabs': "[data-testid='experiment-detail-tabs']",
      'main': "[data-slot='main']",
      'bottom': "[data-testid='experiment-detail-bottom']",
    },
    targetThresholds: {
      "shell": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "rail": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "header": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.11
      },
      "meta": {
        "x": 4,
        "y": 8,
        "widthRatio": 0.03,
        "heightRatio": 0.03
      },
      "tabs": {
        "x": 4,
        "y": 8,
        "widthRatio": 0.03,
        "heightRatio": 0.03
      },
      "main": {
        "x": 4,
        "y": 8,
        "widthRatio": 0.03,
        "heightRatio": 0.03
      },
      "bottom": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.03
      }
    },
    visualThresholds: {
      "consoleErrors": 0,
      "pageErrors": 0,
      "missingSelectors": 0,
      "targetMismatch": 0,
      "pixelDiffRatio": 0.075
    },
  },
  {
    route: "/research/experiments",
    name: "experiment-list",
    prototype: "page-experiment-list.html",
    prototypeTargets: {
      'shell': "#default-view > [class*='shell']",
      'rail': ".shell-rail",
      'header': ".shell-header",
      'toolbar': ".filter-toolbar",
      'main': ".catalog-table",
      'detail': ".catalog-detail",
    },
    reactTargets: {
      'shell': "#root > div",
      'rail': "nav[aria-label='主导航']",
      'header': "header",
      'toolbar': "[data-slot='toolbar']",
      'main': "[data-slot='main']",
      'detail': "[data-slot='detail']",
    },
    targetThresholds: {
      "shell": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "rail": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "header": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "toolbar": {
        "x": 6,
        "y": 44,
        "widthRatio": 0.03,
        "heightRatio": 0.55
      },
      "main": {
        "x": 10,
        "y": 22,
        "widthRatio": 0.05,
        "heightRatio": 0.08
      },
      "detail": {
        "x": 22,
        "y": 60,
        "widthRatio": 0.2,
        "heightRatio": 0.14
      }
    },
    visualThresholds: {
      "consoleErrors": 0,
      "pageErrors": 0,
      "missingSelectors": 0,
      "targetMismatch": 0,
      "pixelDiffRatio": 0.065
    },
  },
  {
    route: "/research/factors/$id",
    name: "factor-analysis",
    prototype: "page-factor-analysis.html",
    prototypeTargets: {
      'shell': "#default-view > [class*='shell']",
      'rail': ".shell-rail",
      'header': ".shell-header",
      'meta': ".hub-meta",
      'main': "[data-contract-slot='main']",
      'sidebar': "[data-contract-slot='sidebar']",
    },
    reactTargets: {
      'shell': "#root > div",
      'rail': "nav[aria-label='主导航']",
      'header': "[data-slot='header']",
      'meta': "[data-slot='meta']",
      'main': "[data-slot='main']",
      'sidebar': "[data-testid='factor-analysis-sidebar']",
    },
    targetThresholds: {
      "shell": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "rail": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "header": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.11
      },
      "meta": {
        "x": 4,
        "y": 56,
        "widthRatio": 0.03,
        "heightRatio": 0.85
      },
      "main": {
        "x": 8,
        "y": 52,
        "widthRatio": 0.03,
        "heightRatio": 0.12
      },
      "sidebar": {
        "x": 8,
        "y": 52,
        "widthRatio": 0.03,
        "heightRatio": 0.12
      }
    },
    visualThresholds: {
      "consoleErrors": 0,
      "pageErrors": 0,
      "missingSelectors": 0,
      "targetMismatch": 0,
      "pixelDiffRatio": 0.04
    },
  },
  {
    route: "/research/factors",
    name: "factor-list",
    prototype: "page-factor-list.html",
    prototypeTargets: {
      'shell': "#default-view > [class*='shell']",
      'rail': ".shell-rail",
      'header': ".shell-header",
      'toolbar': ".filter-toolbar",
      'main': "[data-contract-slot='main']",
      'detail': "[data-contract-slot='detail']",
    },
    reactTargets: {
      'shell': "#root > div",
      'rail': "nav[aria-label='主导航']",
      'header': "header",
      'toolbar': "[data-testid='factor-catalog-filters']",
      'main': "[data-slot='main']",
      'detail': "[data-testid='factor-catalog-detail']",
    },
    targetThresholds: {
      "shell": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "rail": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "header": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "toolbar": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "main": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "detail": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      }
    },
    visualThresholds: {
      "consoleErrors": 0,
      "pageErrors": 0,
      "missingSelectors": 0,
      "targetMismatch": 0,
      "pixelDiffRatio": 0.055
    },
  },
  {
    route: "/",
    name: "home",
    prototype: "page-home.html",
    prototypeTargets: {
      'shell': "#default-view > [class*='shell']",
      'rail': ".shell-rail",
      'header': ".shell-header",
      'pulse': ".shell-status-bar",
      'main': ".shell-main",
      'sidebar': ".shell-sidebar",
      'decision-banner': "[data-contract-slot='decision-card']",
      'priority-queue': "[data-contract-slot='pending-actions']",
      'secondary': "[data-contract-slot='recent-signals']",
    },
    reactTargets: {
      'shell': "#root > div",
      'rail': "nav[aria-label='主导航']",
      'header': "header",
      'pulse': "[data-slot='pulse-strip']",
      'main': "[data-slot='main']",
      'sidebar': "[data-slot='sidebar-rail']",
      'decision-banner': "[data-testid='decision-banner']",
      'priority-queue': "[data-testid='priority-queue']",
      'secondary': "[data-slot='home-secondary']",
    },
    targetThresholds: {
      "shell": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "rail": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "header": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "pulse": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "main": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "sidebar": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "decision-banner": {
        "x": 8,
        "y": 8,
        "widthRatio": 0.05,
        "heightRatio": 0.05
      },
      "priority-queue": {
        "x": 8,
        "y": 8,
        "widthRatio": 0.05,
        "heightRatio": 0.05
      },
      "secondary": {
        "x": 8,
        "y": 8,
        "widthRatio": 0.05,
        "heightRatio": 0.05
      }
    },
    visualThresholds: {
      "consoleErrors": 0,
      "pageErrors": 0,
      "missingSelectors": 0,
      "targetMismatch": 0,
      "pixelDiffRatio": 0.05
    },
  },
  {
    route: "/instruments/$id",
    resolvedRoute: "/instruments/1000001",
    name: "instrument-hub",
    prototype: "page-instrument-hub.html",
    prototypeTargets: {
      'shell': "#default-view > [class*='shell']",
      'rail': ".shell-rail",
      'header': ".shell-header",
      'meta': ".object-header",
      'tabs': ".hub-tabs",
      'main': ".hub-main",
      'bottom': ".hub-bottom",
      'status': ".status-bar",
    },
    reactTargets: {
      'shell': "#root > div",
      'rail': "nav[aria-label='主导航']",
      'header': "[data-slot='header']",
      'meta': "[data-slot='meta']",
      'tabs': "[data-testid='object-hub-tabs']",
      'main': "[data-slot='main']",
      'bottom': "[data-slot='bottom']",
      'status': "[data-slot='status-bar']",
    },
    targetThresholds: {
      "shell": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "rail": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "header": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.11
      },
      "meta": {
        "x": 200,
        "y": 64,
        "widthRatio": 1,
        "heightRatio": 0.12
      },
      "tabs": {
        "x": 4,
        "y": 24,
        "widthRatio": 0.03,
        "heightRatio": 0.2
      },
      "main": {
        "x": 4,
        "y": 24,
        "widthRatio": 0.36,
        "heightRatio": 0.31
      },
      "bottom": {
        "x": 4,
        "y": 165,
        "widthRatio": 0.36,
        "heightRatio": 0.82
      },
      "status": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      }
    },
    visualThresholds: {
      "consoleErrors": 0,
      "pageErrors": 0,
      "missingSelectors": 0,
      "targetMismatch": 0,
      "pixelDiffRatio": 0.04
    },
  },
  {
    route: "/portfolio/manual",
    name: "manual-account",
    prototype: "page-portfolio.html",
    prototypeTargets: {
      'shell': "#default-view > [class*='shell']",
      'rail': ".shell-rail",
      'header': ".shell-header",
      'strip': "[data-contract-slot='strip']",
      'main': "[data-contract-slot='main']",
      'activity': "[data-contract-slot='right-rail']",
      'analysis': "[data-contract-slot='analysis']",
    },
    reactTargets: {
      'shell': "#root > div",
      'rail': "nav[aria-label='主导航']",
      'header': "header",
      'strip': "[data-slot='strip']",
      'main': "[data-slot='main']",
      'activity': "[data-slot='activity']",
      'analysis': "[data-slot='analysis']",
    },
    targetThresholds: {
      "shell": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "rail": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "header": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "strip": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "main": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "activity": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "analysis": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      }
    },
    visualThresholds: {
      "consoleErrors": 0,
      "pageErrors": 0,
      "missingSelectors": 0,
      "targetMismatch": 0,
      "pixelDiffRatio": 0.02
    },
  },
  {
    route: "/markets/industries",
    name: "markets-industries",
    prototype: "page-markets-screener.html",
    prototypeTargets: {
      'shell': "#default-view > [class*='shell']",
      'rail': ".shell-rail",
      'header': ".shell-header",
      'toolbar': ".filter-toolbar",
      'main': ".catalog-table",
      'detail': ".catalog-detail",
    },
    reactTargets: {
      'shell': "#root > div",
      'rail': "nav[aria-label='主导航']",
      'header': "header",
      'toolbar': "[data-slot='toolbar']",
      'main': "[data-slot='main']",
      'detail': "[data-slot='detail']",
    },
    targetThresholds: {
      "shell": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "rail": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "header": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "toolbar": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 1
      },
      "main": {
        "x": 4,
        "y": 190,
        "widthRatio": 0.03,
        "heightRatio": 0.41
      },
      "detail": {
        "x": 4,
        "y": 36,
        "widthRatio": 0.03,
        "heightRatio": 0.06
      }
    },
    visualThresholds: {
      "consoleErrors": 0,
      "pageErrors": 0,
      "missingSelectors": 0,
      "targetMismatch": 0,
      "pixelDiffRatio": 0.04
    },
  },
  {
    route: "/markets/screener",
    name: "markets-screener",
    prototype: "page-markets-screener.html",
    prototypeTargets: {
      'shell': "#default-view > [class*='shell']",
      'rail': ".shell-rail",
      'header': ".shell-header",
      'toolbar': ".filter-toolbar",
      'main': ".catalog-table",
      'detail': ".catalog-detail",
    },
    reactTargets: {
      'shell': "#root > div",
      'rail': "nav[aria-label='主导航']",
      'header': "header",
      'toolbar': "[data-slot='toolbar']",
      'main': "[data-slot='main']",
      'detail': "[data-slot='detail']",
    },
    targetThresholds: {
      "shell": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "rail": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "header": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "toolbar": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 1
      },
      "main": {
        "x": 4,
        "y": 190,
        "widthRatio": 0.03,
        "heightRatio": 0.41
      },
      "detail": {
        "x": 4,
        "y": 36,
        "widthRatio": 0.03,
        "heightRatio": 0.06
      }
    },
    visualThresholds: {
      "consoleErrors": 0,
      "pageErrors": 0,
      "missingSelectors": 0,
      "targetMismatch": 0,
      "pixelDiffRatio": 0.04
    },
  },
  {
    route: "/portfolio/model",
    name: "model-portfolio",
    prototype: "page-portfolio.html",
    prototypeTargets: {
      'shell': "#default-view > [class*='shell']",
      'rail': ".shell-rail",
      'header': ".shell-header",
      'strip': "[data-contract-slot='strip']",
      'main': "[data-contract-slot='main']",
      'activity': "[data-contract-slot='right-rail']",
      'analysis': "[data-contract-slot='analysis']",
    },
    reactTargets: {
      'shell': "#root > div",
      'rail': "nav[aria-label='主导航']",
      'header': "header",
      'strip': "[data-slot='strip']",
      'main': "[data-slot='main']",
      'activity': "[data-slot='activity']",
      'analysis': "[data-slot='analysis']",
    },
    targetThresholds: {
      "shell": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "rail": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "header": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "strip": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "main": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "activity": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "analysis": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      }
    },
    visualThresholds: {
      "consoleErrors": 0,
      "pageErrors": 0,
      "missingSelectors": 0,
      "targetMismatch": 0,
      "pixelDiffRatio": 0.02
    },
  },
  {
    route: "/portfolio/paper",
    name: "paper-account",
    prototype: "page-portfolio.html",
    prototypeTargets: {
      'shell': "#default-view > [class*='shell']",
      'rail': ".shell-rail",
      'header': ".shell-header",
      'strip': "[data-contract-slot='strip']",
      'main': "[data-contract-slot='main']",
      'activity': "[data-contract-slot='right-rail']",
      'analysis': "[data-contract-slot='analysis']",
    },
    reactTargets: {
      'shell': "#root > div",
      'rail': "nav[aria-label='主导航']",
      'header': "header",
      'strip': "[data-slot='strip']",
      'main': "[data-slot='main']",
      'activity': "[data-slot='activity']",
      'analysis': "[data-slot='analysis']",
    },
    targetThresholds: {
      "shell": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "rail": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "header": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "strip": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "main": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "activity": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "analysis": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      }
    },
    visualThresholds: {
      "consoleErrors": 0,
      "pageErrors": 0,
      "missingSelectors": 0,
      "targetMismatch": 0,
      "pixelDiffRatio": 0.02
    },
  },
  {
    route: "/portfolio",
    name: "portfolio-overview",
    prototype: "page-portfolio.html",
    prototypeTargets: {
      'shell': "#default-view > [class*='shell']",
      'rail': ".shell-rail",
      'header': ".shell-header",
      'strip': "[data-contract-slot='strip']",
      'main': "[data-contract-slot='main']",
      'activity': "[data-contract-slot='right-rail']",
      'analysis': "[data-contract-slot='analysis']",
    },
    reactTargets: {
      'shell': "#root > div",
      'rail': "nav[aria-label='主导航']",
      'header': "header",
      'strip': "[data-slot='strip']",
      'main': "[data-slot='main']",
      'activity': "[data-slot='activity']",
      'analysis': "[data-slot='analysis']",
    },
    targetThresholds: {
      "shell": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "rail": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "header": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "strip": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "main": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "activity": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "analysis": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      }
    },
    visualThresholds: {
      "consoleErrors": 0,
      "pageErrors": 0,
      "missingSelectors": 0,
      "targetMismatch": 0,
      "pixelDiffRatio": 0.02
    },
  },
  {
    route: "/portfolio/risk",
    name: "portfolio-risk",
    prototype: "page-risk-center.html",
    prototypeTargets: {
      'shell': "#default-view > [class*='shell']",
      'rail': ".shell-rail",
      'header': ".shell-header",
      'strip': "[data-contract-slot='risk-strip']",
      'main': "[data-contract-slot='risk-dashboard']",
      'activity': "[data-contract-slot='right-rail']",
      'analysis': "[data-contract-slot='analysis-band']",
      'status': ".status-bar",
    },
    reactTargets: {
      'shell': "#root > div",
      'rail': "nav[aria-label='主导航']",
      'header': "header",
      'strip': "[data-testid='risk-primary-strip']",
      'main': "[data-testid='risk-dashboard']",
      'activity': "[data-testid='risk-activity-rail']",
      'analysis': "[data-testid='risk-analysis-band']",
      'status': "[data-slot='status-bar']",
    },
    targetThresholds: {
      "shell": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "rail": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "header": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "strip": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "main": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "activity": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "analysis": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "status": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      }
    },
    visualThresholds: {
      "consoleErrors": 0,
      "pageErrors": 0,
      "missingSelectors": 0,
      "targetMismatch": 0,
      "pixelDiffRatio": 0.021
    },
  },
  {
    route: "/portfolio/transactions",
    name: "portfolio-transactions",
    prototype: "page-orders-ledger.html",
    prototypeTargets: {
      'shell': "#default-view > [class*='shell']",
      'rail': ".shell-rail",
      'header': ".shell-header",
      'health': ".status-strip",
      'main': ".ledger-table-area",
      'detail': ".order-trace",
      'status': ".status-bar",
    },
    reactTargets: {
      'shell': "#root > div",
      'rail': "nav[aria-label='主导航']",
      'header': "header",
      'health': "[data-slot='health']",
      'main': "[data-testid='orders-ledger-main']",
      'detail': "[data-slot='detail']",
      'status': "[data-slot='status-bar']",
    },
    targetThresholds: {
      "shell": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "rail": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "header": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "health": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "main": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "detail": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "status": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      }
    },
    visualThresholds: {
      "consoleErrors": 0,
      "pageErrors": 0,
      "missingSelectors": 0,
      "targetMismatch": 0,
      "pixelDiffRatio": 0.05
    },
  },
  {
    route: "/research/agent",
    name: "research-agent-lab",
    prototype: "page-agent-console-v2.html",
    prototypeTargets: {
      'shell': ".agent-shell",
      'rail': ".shell-rail",
      'header': ".agent-header",
      'tabs': ".agent-tabs",
      'source': ".list-panel",
      'main': ".main-panel",
      'inspector': ".inspector",
      'status': ".status-bar",
    },
    reactTargets: {
      'shell': "[data-slot='app-shell']",
      'rail': "nav[aria-label='主导航']",
      'header': "[data-slot='header']",
      'tabs': "[data-slot='task-toolbar']",
      'source': "[data-slot='source']",
      'main': "[data-slot='main']",
      'inspector': "[data-slot='inspector']",
      'status': "[data-slot='status-bar']",
    },
    targetThresholds: {
      "shell": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "rail": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "header": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "tabs": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "source": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "main": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "inspector": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "status": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      }
    },
    visualThresholds: {
      "consoleErrors": 0,
      "pageErrors": 0,
      "missingSelectors": 0,
      "targetMismatch": 0,
      "pixelDiffRatio": 0.05
    },
  },
  {
    route: "/research",
    name: "research",
    prototype: "page-research.html",
    prototypeTargets: {
      'shell': "#default-view > [class*='shell']",
      'rail': ".shell-rail",
      'header': ".shell-header",
      'strip': "[data-contract-slot='strip']",
      'main': "[data-contract-slot='main']",
      'activity': "[data-contract-slot='activity']",
      'analysis': "[data-contract-slot='analysis']",
      'factor-monitor': "#panel-factors .monitor-panel",
      'research-activity': "#panel-factors .activity-stack",
    },
    reactTargets: {
      'shell': "#root > div",
      'rail': "nav[aria-label='主导航']",
      'header': "header",
      'strip': "[data-slot='strip']",
      'main': "[data-slot='main']",
      'activity': "[data-slot='activity']",
      'analysis': "[data-slot='analysis']",
      'factor-monitor': "[data-testid='research-factor-monitor']",
      'research-activity': "[data-testid='research-activity']",
    },
    targetThresholds: {
      "shell": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "rail": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "header": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "strip": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "main": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "activity": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "analysis": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "factor-monitor": {
        "x": 8,
        "y": 8,
        "widthRatio": 0.05,
        "heightRatio": 0.05
      },
      "research-activity": {
        "x": 8,
        "y": 8,
        "widthRatio": 0.05,
        "heightRatio": 0.05
      }
    },
    visualThresholds: {
      "consoleErrors": 0,
      "pageErrors": 0,
      "missingSelectors": 0,
      "targetMismatch": 0,
      "pixelDiffRatio": 0.051
    },
  },
  {
    route: "/research/reviews/$id",
    resolvedRoute: "/research/reviews/exp-rotation-v4?strategyId=seed_etf_industry_rotation&version=4",
    name: "review-detail",
    prototype: "page-strategies-detail.html",
    prototypeTargets: {
      'shell': "#default-view > [class*='shell']",
      'rail': ".shell-rail",
      'header': ".shell-header",
      'meta': ".hub-meta",
      'tabs': ".hub-tabs",
      'main': "[data-contract-slot='main']",
      'bottom': ".hub-bottom",
    },
    reactTargets: {
      'shell': "#root > div",
      'rail': "nav[aria-label='主导航']",
      'header': "[data-slot='header']",
      'meta': "[data-testid='review-detail-meta']",
      'tabs': "[data-testid='review-detail-tabs']",
      'main': "[data-slot='main']",
      'bottom': "[data-testid='review-detail-bottom']",
    },
    targetThresholds: {
      "shell": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "rail": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "header": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.11
      },
      "meta": {
        "x": 4,
        "y": 8,
        "widthRatio": 0.03,
        "heightRatio": 0.03
      },
      "tabs": {
        "x": 4,
        "y": 8,
        "widthRatio": 0.03,
        "heightRatio": 0.03
      },
      "main": {
        "x": 4,
        "y": 8,
        "widthRatio": 0.03,
        "heightRatio": 0.03
      },
      "bottom": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.03
      }
    },
    visualThresholds: {
      "consoleErrors": 0,
      "pageErrors": 0,
      "missingSelectors": 0,
      "targetMismatch": 0,
      "pixelDiffRatio": 0.075
    },
  },
  {
    route: "/research/reviews",
    name: "review-list",
    prototype: "page-experiment-list.html",
    prototypeTargets: {
      'shell': "#default-view > [class*='shell']",
      'rail': ".shell-rail",
      'header': ".shell-header",
      'toolbar': ".filter-toolbar",
      'main': ".catalog-table",
      'detail': ".catalog-detail",
    },
    reactTargets: {
      'shell': "#root > div",
      'rail': "nav[aria-label='主导航']",
      'header': "header",
      'toolbar': "[data-slot='toolbar']",
      'main': "[data-slot='main']",
      'detail': "[data-slot='detail']",
    },
    targetThresholds: {
      "shell": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "rail": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "header": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "toolbar": {
        "x": 6,
        "y": 44,
        "widthRatio": 0.03,
        "heightRatio": 0.55
      },
      "main": {
        "x": 10,
        "y": 22,
        "widthRatio": 0.05,
        "heightRatio": 0.08
      },
      "detail": {
        "x": 22,
        "y": 60,
        "widthRatio": 0.2,
        "heightRatio": 0.14
      }
    },
    visualThresholds: {
      "consoleErrors": 0,
      "pageErrors": 0,
      "missingSelectors": 0,
      "targetMismatch": 0,
      "pixelDiffRatio": 0.065
    },
  },
  {
    route: "/portfolio/review",
    name: "signals-inbox",
    prototype: "page-signals-inbox.html",
    prototypeTargets: {
      'shell': "#default-view > [class*='shell']",
      'rail': ".shell-rail",
      'header': ".shell-header",
      'health': ".scope-strip",
      'main': ".signals-main",
      'detail': ".detail-panel",
      'status': ".status-bar",
    },
    reactTargets: {
      'shell': "#root > div",
      'rail': "nav[aria-label='主导航']",
      'header': "header",
      'health': "[data-slot='health']",
      'main': "[data-slot='main']",
      'detail': "[data-slot='detail']",
      'status': "[data-slot='status-bar']",
    },
    targetThresholds: {
      "shell": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "rail": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "header": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "health": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "main": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "detail": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "status": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      }
    },
    visualThresholds: {
      "consoleErrors": 0,
      "pageErrors": 0,
      "missingSelectors": 0,
      "targetMismatch": 0,
      "pixelDiffRatio": 0.05
    },
  },
  {
    route: "/research/strategies/$id",
    name: "strategies-detail",
    prototype: "page-strategies-detail.html",
    prototypeTargets: {
      'shell': "#default-view > [class*='shell']",
      'rail': ".shell-rail",
      'header': ".shell-header",
      'meta': ".hub-meta",
      'tabs': ".hub-tabs",
      'main': "[data-contract-slot='main']",
      'bottom': ".hub-bottom",
    },
    reactTargets: {
      'shell': "#root > div",
      'rail': "nav[aria-label='主导航']",
      'header': "[data-slot='header']",
      'meta': "[data-testid='strategy-detail-meta']",
      'tabs': "[data-testid='strategy-detail-tabs']",
      'main': "[data-slot='main']",
      'bottom': "[data-testid='strategy-detail-bottom']",
    },
    targetThresholds: {
      "shell": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "rail": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "header": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.11
      },
      "meta": {
        "x": 4,
        "y": 8,
        "widthRatio": 0.03,
        "heightRatio": 0.03
      },
      "tabs": {
        "x": 4,
        "y": 8,
        "widthRatio": 0.03,
        "heightRatio": 0.03
      },
      "main": {
        "x": 4,
        "y": 8,
        "widthRatio": 0.03,
        "heightRatio": 0.03
      },
      "bottom": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.03
      }
    },
    visualThresholds: {
      "consoleErrors": 0,
      "pageErrors": 0,
      "missingSelectors": 0,
      "targetMismatch": 0,
      "pixelDiffRatio": 0.065
    },
  },
  {
    route: "/research/strategies",
    name: "strategy-list",
    prototype: "page-strategy-list.html",
    prototypeTargets: {
      'shell': "#default-view > [class*='shell']",
      'rail': ".shell-rail",
      'header': ".shell-header",
      'toolbar': "[data-contract-slot='header']",
      'main': "[data-contract-slot='main']",
      'detail': "[data-contract-slot='detail']",
      'governance-summary': ".perf-summary",
    },
    reactTargets: {
      'shell': "#root > div",
      'rail': "nav[aria-label='主导航']",
      'header': "header",
      'toolbar': "[data-testid='strategy-catalog-filters']",
      'main': "[data-testid='strategy-catalog-main']",
      'detail': "[data-testid='strategy-catalog-detail']",
      'governance-summary': "[data-testid='strategy-catalog-summary']",
    },
    targetThresholds: {
      "shell": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "rail": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "header": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "toolbar": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "main": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "detail": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "governance-summary": {
        "x": 8,
        "y": 8,
        "widthRatio": 0.05,
        "heightRatio": 0.05
      }
    },
    visualThresholds: {
      "consoleErrors": 0,
      "pageErrors": 0,
      "missingSelectors": 0,
      "targetMismatch": 0,
      "pixelDiffRatio": 0.055
    },
  },
  {
    route: "/research/strategies/$id/studio",
    name: "strategy-studio",
    prototype: "page-strategy-studio.html",
    prototypeTargets: {
      'shell': "#default-view > [class*='shell']",
      'rail': ".shell-rail",
      'header': ".studio-header",
      'modes': ".studio-mode-bar",
      'source': ".studio-sources",
      'main': ".studio-main",
      'inspector': ".studio-inspector",
      'logs': ".studio-logs",
      'status': ".status-bar",
    },
    reactTargets: {
      'shell': "#root > div",
      'rail': "nav[aria-label='主导航']",
      'header': "[data-slot='header']",
      'modes': "[data-slot='modes']",
      'source': "[data-slot='source']",
      'main': "[data-slot='main']",
      'inspector': "[data-slot='inspector']",
      'logs': "[data-slot='logs']",
      'status': "[data-slot='status-bar']",
    },
    targetThresholds: {
      "shell": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "rail": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "header": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.11
      },
      "modes": {
        "x": 4,
        "y": 6,
        "widthRatio": 0.03,
        "heightRatio": 0.08
      },
      "source": {
        "x": 8,
        "y": 8,
        "widthRatio": 0.3,
        "heightRatio": 0.08
      },
      "main": {
        "x": 8,
        "y": 8,
        "widthRatio": 0.08,
        "heightRatio": 0.08
      },
      "inspector": {
        "x": 8,
        "y": 8,
        "widthRatio": 0.12,
        "heightRatio": 0.08
      },
      "logs": {
        "x": 8,
        "y": 18,
        "widthRatio": 0.03,
        "heightRatio": 0.55
      },
      "status": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      }
    },
    visualThresholds: {
      "consoleErrors": 0,
      "pageErrors": 0,
      "missingSelectors": 0,
      "targetMismatch": 0,
      "pixelDiffRatio": 0.065
    },
  },
  {
    route: "/system/agent",
    name: "system-agent-ops",
    prototype: "page-agent-console-v2.html",
    prototypeTargets: {
      'shell': ".agent-shell",
      'rail': ".shell-rail",
      'header': ".agent-header",
      'tabs': ".agent-tabs",
      'source': ".list-panel",
      'main': ".main-panel",
      'inspector': ".inspector",
      'status': ".status-bar",
    },
    reactTargets: {
      'shell': "[data-slot='app-shell']",
      'rail': "nav[aria-label='主导航']",
      'header': "[data-slot='header']",
      'tabs': "[data-slot='task-toolbar']",
      'source': "[data-slot='source']",
      'main': "[data-slot='main']",
      'inspector': "[data-slot='inspector']",
      'status': "[data-slot='status-bar']",
    },
    targetThresholds: {
      "shell": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "rail": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "header": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "tabs": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "source": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "main": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "inspector": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "status": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      }
    },
    visualThresholds: {
      "consoleErrors": 0,
      "pageErrors": 0,
      "missingSelectors": 0,
      "targetMismatch": 0,
      "pixelDiffRatio": 0.05
    },
  },
  {
    route: "/system/audit",
    name: "system-audit",
    prototype: "page-platform.html",
    prototypeTargets: {
      'shell': "#default-view > [class*='shell']",
      'rail': ".shell-rail",
      'header': ".shell-header",
      'health': ".ops-health",
      'main': ".ops-main",
      'detail': ".ops-detail",
      'status': ".status-bar",
    },
    reactTargets: {
      'shell': "#root > div",
      'rail': "nav[aria-label='主导航']",
      'header': "header",
      'health': "[data-slot='health']",
      'main': "[data-slot='main']",
      'detail': "[data-slot='detail']",
      'status': "[data-slot='status-bar']",
    },
    targetThresholds: {
      "shell": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "rail": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "header": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "health": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "main": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "detail": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "status": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      }
    },
    visualThresholds: {
      "consoleErrors": 0,
      "pageErrors": 0,
      "missingSelectors": 0,
      "targetMismatch": 0,
      "pixelDiffRatio": 0.07
    },
  },
  {
    route: "/system/jobs",
    name: "system-jobs",
    prototype: "page-platform.html",
    prototypeTargets: {
      'shell': "#default-view > [class*='shell']",
      'rail': ".shell-rail",
      'header': ".shell-header",
      'health': ".ops-health",
      'main': ".ops-main",
      'detail': ".ops-detail",
      'status': ".status-bar",
    },
    reactTargets: {
      'shell': "#root > div",
      'rail': "nav[aria-label='主导航']",
      'header': "header",
      'health': "[data-slot='health']",
      'main': "[data-slot='main']",
      'detail': "[data-slot='detail']",
      'status': "[data-slot='status-bar']",
    },
    targetThresholds: {
      "shell": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "rail": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "header": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "health": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "main": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "detail": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "status": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      }
    },
    visualThresholds: {
      "consoleErrors": 0,
      "pageErrors": 0,
      "missingSelectors": 0,
      "targetMismatch": 0,
      "pixelDiffRatio": 0.07
    },
  },
  {
    route: "/system/settings",
    name: "system-settings",
    prototype: "page-platform-settings.html",
    prototypeTargets: {
      'shell': "#default-view > [class*='shell']",
      'rail': ".shell-rail",
      'header': ".shell-header",
      'health': ".ops-health",
      'main': ".ops-main",
      'detail': ".ops-detail",
    },
    reactTargets: {
      'shell': "#root > div",
      'rail': "nav[aria-label='主导航']",
      'header': "header",
      'health': "[data-slot='health']",
      'main': "[data-slot='main']",
      'detail': "[data-slot='detail']",
    },
    targetThresholds: {
      "shell": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "rail": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "header": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "health": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "main": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "detail": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      }
    },
    visualThresholds: {
      "consoleErrors": 0,
      "pageErrors": 0,
      "missingSelectors": 0,
      "targetMismatch": 0,
      "pixelDiffRatio": 0.04
    },
  },
  {
    route: "/system",
    name: "system",
    prototype: "page-platform.html",
    prototypeTargets: {
      'shell': "#default-view > [class*='shell']",
      'rail': ".shell-rail",
      'header': ".shell-header",
      'health': ".ops-health",
      'main': ".ops-main",
      'detail': ".ops-detail",
      'status': ".status-bar",
    },
    reactTargets: {
      'shell': "#root > div",
      'rail': "nav[aria-label='主导航']",
      'header': "header",
      'health': "[data-slot='health']",
      'main': "[data-slot='main']",
      'detail': "[data-slot='detail']",
      'status': "[data-slot='status-bar']",
    },
    targetThresholds: {
      "shell": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "rail": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "header": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "health": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "main": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "detail": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "status": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      }
    },
    visualThresholds: {
      "consoleErrors": 0,
      "pageErrors": 0,
      "missingSelectors": 0,
      "targetMismatch": 0,
      "pixelDiffRatio": 0.07
    },
  },
  {
    route: "/research/universes",
    name: "universe-list",
    prototype: "page-universe-list.html",
    prototypeTargets: {
      'shell': "#default-view > [class*='shell']",
      'rail': ".shell-rail",
      'header': ".shell-header",
      'toolbar': ".universe-kpi-strip",
      'main': ".catalog-table",
      'detail': ".catalog-detail",
    },
    reactTargets: {
      'shell': "#root > div",
      'rail': "nav[aria-label='主导航']",
      'header': "header",
      'toolbar': "[data-slot='toolbar']",
      'main': "[data-slot='main']",
      'detail': "[data-slot='detail']",
    },
    targetThresholds: {
      "shell": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "rail": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "header": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "toolbar": {
        "x": 6,
        "y": 6,
        "widthRatio": 0.03,
        "heightRatio": 0.08
      },
      "main": {
        "x": 10,
        "y": 22,
        "widthRatio": 0.08,
        "heightRatio": 0.12
      },
      "detail": {
        "x": 22,
        "y": 60,
        "widthRatio": 0.2,
        "heightRatio": 0.16
      }
    },
    visualThresholds: {
      "consoleErrors": 0,
      "pageErrors": 0,
      "missingSelectors": 0,
      "targetMismatch": 0,
      "pixelDiffRatio": 0.075
    },
  },
  {
    route: "/markets/watchlist",
    name: "watchlist",
    prototype: "page-watchlist.html",
    prototypeTargets: {
      'shell': "#default-view > [class*='shell']",
      'rail': ".shell-rail",
      'header': ".shell-header",
      'toolbar': ".filter-toolbar",
      'main': ".catalog-table",
      'detail': ".catalog-detail",
    },
    reactTargets: {
      'shell': "#root > div",
      'rail': "nav[aria-label='主导航']",
      'header': "header",
      'toolbar': "[data-slot='toolbar']",
      'main': "[data-testid='watchlist-catalog']",
      'detail': "[data-slot='detail']",
    },
    targetThresholds: {
      "shell": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "rail": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "header": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 0.05
      },
      "toolbar": {
        "x": 4,
        "y": 4,
        "widthRatio": 0.03,
        "heightRatio": 1
      },
      "main": {
        "x": 4,
        "y": 48,
        "widthRatio": 0.03,
        "heightRatio": 0.08
      },
      "detail": {
        "x": 4,
        "y": 36,
        "widthRatio": 0.03,
        "heightRatio": 0.06
      }
    },
    visualThresholds: {
      "consoleErrors": 0,
      "pageErrors": 0,
      "missingSelectors": 0,
      "targetMismatch": 0,
      "pixelDiffRatio": 0.04
    },
  },
];
