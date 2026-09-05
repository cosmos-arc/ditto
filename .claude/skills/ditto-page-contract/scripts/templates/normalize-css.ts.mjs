/**
 * Prototype Normalization CSS
 *
 * 注入到 prototype 页面后用于标准化渲染环境，
 * 隐藏导航 UI、强制 100vh、固定 status-bar 高度。
 */

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
`;
