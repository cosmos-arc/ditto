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
  #default-view > .status-bar {
    height: 24px !important;
    flex: 0 0 auto !important;
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
    route: "/",
    name: "home",
    prototype: "page-home.html",
    prototypeTargets: {
      'rail': ".shell-rail",
      'header': ".shell-header",
      'pulse': ".shell-pulse",
      'main': ".shell-main",
      'sidebar': ".shell-sidebar",
      'decision-banner': ".decision-banner",
      'priority-queue': ".panel-grow",
      'secondary': ".shell-secondary",
    },
    reactTargets: {
      'shell': "#root > div",
      'rail': "nav[aria-label='主导航']",
      'header': "header",
      'pulse': "[data-slot='pulse-strip']",
      'main': "[data-slot='main']",
      'sidebar': "[data-slot='sidebar-rail']",
      'decision-banner': "[data-slot='decision-banner']",
      'priority-queue': "[data-testid='priority-queue']",
      'secondary': "[data-slot='home-secondary']",
    },
  },
];
