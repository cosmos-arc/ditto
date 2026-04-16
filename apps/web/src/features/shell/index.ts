export { AppShell } from "./components/app-shell";
export { NoiseLayer } from "./components/noise-layer";
export { Panel, PanelBody, PanelHeader } from "./components/panel";
export { Rail } from "./components/rail";
export { ShellHeader } from "./components/header";
export { StatusBar } from "./components/status-bar";
export { ThemeSwitcher } from "./components/theme-switcher";
export { AnalyticalLayout } from "./layouts/analytical.layout";
export { CatalogLayout } from "./layouts/catalog.layout";
export { CommandCenterLayout } from "./layouts/command-center.layout";
export { ObjectHubLayout } from "./layouts/object-hub.layout";
export { OpsConsoleLayout } from "./layouts/ops-console.layout";
export { RadarLayout } from "./layouts/radar.layout";
export { StudioLayout } from "./layouts/studio.layout";

// Page contracts — legacy (21 routes, hand-authored)
export {
	PAGE_CONTRACTS as LEGACY_PAGE_CONTRACTS,
	SHELL_SLOT_MAP as LEGACY_SHELL_SLOT_MAP,
	PAGE_PATTERNS as LEGACY_PAGE_PATTERNS,
	SHELL_FAMILIES as LEGACY_SHELL_FAMILIES,
	PROTOTYPE_SOURCES as LEGACY_PROTOTYPE_SOURCES,
} from "./page-contracts";
export type {
	PageContract as LegacyPageContract,
	PagePattern as LegacyPagePattern,
	ShellFamily as LegacyShellFamily,
	PrototypeSource as LegacyPrototypeSource,
} from "./page-contracts";

// Page contracts — generated (contract-ready pages only)
export {
	PAGE_CONTRACTS,
	SHELL_SLOT_MAP,
	PAGE_PATTERNS,
	SHELL_FAMILIES,
	PROTOTYPE_SOURCES,
} from "./page-contracts.generated";
export type {
	PageContract,
	PagePattern,
	ShellFamily,
	PrototypeSource,
} from "./page-contracts.generated";
