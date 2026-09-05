import { ViewPreferencesMenu } from "./view-preferences-menu";

/**
 * Backwards-compatible alias for the account-scoped view preferences menu.
 * ShellHeader uses HeaderUtilityBar directly.
 */
export function ThemeSwitcher() {
	return <ViewPreferencesMenu />;
}
