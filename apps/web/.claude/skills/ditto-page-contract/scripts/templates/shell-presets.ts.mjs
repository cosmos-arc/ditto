/**
 * Shell Family 级别的 React target 预设
 *
 * 每个预设定义该 shell family 的默认 data-slot 选择器映射。
 * 生成器将页面合同的 slots[] 与预设 merge，得到完整的 React target map。
 */

export const SHELL_REACT_PRESETS = {
  "command-center": {
    rail: "nav[aria-label='主导航']",
    header: "header",
    strip: "[data-slot='pulse-strip']",
    main: "[data-slot='main']",
    sidebar: "[data-slot='sidebar-rail']",
    statusSlot: "[data-slot='status']",
    status: "[data-slot='status-bar']",
  },
  analytical: {
    rail: "nav[aria-label='主导航']",
    header: "header",
    strip: "[data-slot='strip']",
    banner: "[data-slot='banner']",
    main: "[data-slot='main']",
    activity: "[data-slot='activity']",
    analysis: "[data-slot='analysis']",
    status: "[data-slot='status-bar']",
  },
  catalog: {
    rail: "nav[aria-label='主导航']",
    header: "header",
    toolbar: "[data-slot='toolbar']",
    main: "[data-slot='main']",
    detail: "[data-slot='detail']",
    filter: "[data-slot='filter-toolbar']",
  },
  "object-hub": {
    rail: "nav[aria-label='主导航']",
    header: "header",
    meta: "[data-slot='meta']",
    tabs: "[data-slot='tabs']",
    main: "[data-slot='main']",
    bottom: "[data-slot='bottom']",
    status: "[data-slot='status-bar']",
  },
  studio: {
    rail: "nav[aria-label='主导航']",
    header: "header",
    source: "[data-slot='source']",
    main: "[data-slot='main']",
    inspector: "[data-slot='inspector']",
    logs: "[data-slot='logs']",
    status: "[data-slot='status-bar']",
  },
  "ops-console": {
    rail: "nav[aria-label='主导航']",
    header: "header",
    health: "[data-slot='health']",
    main: "[data-slot='main']",
    detail: "[data-slot='detail']",
    status: "[data-slot='status-bar']",
  },
  radar: {
    rail: "nav[aria-label='主导航']",
    header: "header",
    contextBar: "[data-slot='context-bar']",
    scopeStrip: "[data-slot='scope-strip']",
    main: "[data-slot='main']",
    rightRail: "[data-slot='right-rail']",
    status: "[data-slot='status-bar']",
  },
};

/**
 * Shell Family 对应的 Prototype 级通用选择器
 */
export const SHELL_PROTOTYPE_PRESETS = {
  "command-center": {
    rail: ".shell-rail",
    header: ".shell-header",
  },
  analytical: {
    rail: ".shell-rail",
    header: ".shell-header",
  },
  catalog: {
    rail: ".shell-rail",
    header: ".shell-header",
  },
  "object-hub": {
    rail: ".shell-rail",
    header: ".object-header",
  },
  studio: {
    rail: ".shell-rail",
    header: ".studio-header",
  },
  "ops-console": {
    rail: ".shell-rail",
    header: ".shell-header",
  },
  radar: {
    rail: ".shell-rail",
    header: ".shell-header",
  },
};
