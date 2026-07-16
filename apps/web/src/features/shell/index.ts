export { AppShell } from "./components/app-shell";
export { GlobalCommandButton } from "./components/global-command-button";
export { HeaderUtilityBar } from "./components/header-utility-bar";
export { NoiseLayer } from "./components/noise-layer";
export { Panel, PanelBody, PanelHeader } from "./components/panel";
export { PageTitleBlock } from "./components/page-title-block";
export { Rail } from "./components/rail";
export { ShellHeader } from "./components/header";
export { OverlayProvider, useOverlayController } from "./components/overlay-provider";
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

// Page contracts — generated from docs/contracts/pages/*.contract.json
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
export type { OverlayContract, OverlayKind } from "./overlay-contracts";
