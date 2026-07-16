export { AppShell } from "./components/app-shell";
export { GlobalCommandButton } from "./components/global-command-button";
export { ShellHeader } from "./components/header";
export { HeaderUtilityBar } from "./components/header-utility-bar";
export { NoiseLayer } from "./components/noise-layer";
export { OverlayProvider, useOverlayController } from "./components/overlay-provider";
export { PageTitleBlock } from "./components/page-title-block";
export { Panel, PanelBody, PanelHeader } from "./components/panel";
export { Rail } from "./components/rail";
export { StatusBar } from "./components/status-bar";
export { ThemeSwitcher } from "./components/theme-switcher";
export { ViewPreferencesMenu } from "./components/view-preferences-menu";
export { AnalyticalLayout } from "./layouts/analytical.layout";
export { CatalogLayout } from "./layouts/catalog.layout";
export { CommandCenterLayout } from "./layouts/command-center.layout";
export { ObjectHubLayout } from "./layouts/object-hub.layout";
export { OpsConsoleLayout } from "./layouts/ops-console.layout";
export { RadarLayout } from "./layouts/radar.layout";
export { StudioLayout } from "./layouts/studio.layout";
export type { OverlayContract, OverlayKind } from "./overlay-contracts";
export type {
	PageContract,
	PagePattern,
	PrototypeSource,
	ShellFamily,
} from "./page-contracts.generated";
// Page contracts — generated from docs/contracts/pages/*.contract.json
export {
	PAGE_CONTRACTS,
	PAGE_PATTERNS,
	PROTOTYPE_SOURCES,
	SHELL_FAMILIES,
	SHELL_SLOT_MAP,
} from "./page-contracts.generated";
