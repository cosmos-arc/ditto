import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { CommandCenterLayout } from "./command-center.layout";
import { AnalyticalLayout } from "./analytical.layout";
import { CatalogLayout } from "./catalog.layout";
import { ObjectHubLayout } from "./object-hub.layout";
import { StudioLayout } from "./studio.layout";
import { OpsConsoleLayout } from "./ops-console.layout";
import { RadarLayout } from "./radar.layout";

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

function expectGridRoot(container: HTMLElement) {
	const root = container.firstChild as HTMLElement;
	expect(root.tagName).toBe("DIV");
	expect(root.className).toContain("grid");
	expect(root.className).toContain("h-full");
	expect(root.className).toContain("w-full");
	expect(root.className).toContain("overflow-hidden");
	return root;
}

/* ------------------------------------------------------------------ */
/*  1. CommandCenterLayout                                             */
/* ------------------------------------------------------------------ */

describe("CommandCenterLayout", () => {
	it("renders main children", () => {
		render(
			<CommandCenterLayout main={<span>Main Content</span>} />,
		);
		expect(screen.getByText("Main Content")).toBeInTheDocument();
	});

	it("renders all slots", () => {
		render(
			<CommandCenterLayout
				pulse={<span>Pulse</span>}
				main={<span>Main</span>}
				sidebar={<span>Sidebar</span>}
				status={<span>Status</span>}
			/>,
		);
		expect(screen.getByText("Pulse")).toBeInTheDocument();
		expect(screen.getByText("Main")).toBeInTheDocument();
		expect(screen.getByText("Sidebar")).toBeInTheDocument();
		expect(screen.getByText("Status")).toBeInTheDocument();
	});

	it("omits optional slots when not provided", () => {
		const { container } = render(
			<CommandCenterLayout main={<span>Main</span>} />,
		);
		expect(screen.getByText("Main")).toBeInTheDocument();
		expect(screen.queryByText("Pulse")).not.toBeInTheDocument();
		expect(screen.queryByText("Sidebar")).not.toBeInTheDocument();
		expect(screen.queryByText("Status")).not.toBeInTheDocument();
	});

	it("applies grid layout classes", () => {
		const { container } = render(
			<CommandCenterLayout main={<span>Main</span>} />,
		);
		const root = expectGridRoot(container);
		expect(root.className).toContain("grid-cols-[1fr_var(--width-sidebar)]");
		expect(root.className).toContain("grid-rows-[auto_1fr]");
	});

	it("uses a status row only when status is provided", () => {
		const { container } = render(
			<CommandCenterLayout main={<span>Main</span>} status={<span>Status</span>} />,
		);
		const root = expectGridRoot(container);
		expect(root.className).toContain("grid-rows-[auto_1fr_var(--height-status-bar)]");
		expect(root.className).toContain(
			'[grid-template-areas:"pulse_pulse""main_sidebar""status_status"]',
		);
		expect(screen.getByText("Status")).toBeInTheDocument();
	});

	it("assigns correct grid-area to each slot", () => {
		const { container } = render(
			<CommandCenterLayout
				pulse={<span>Pulse</span>}
				main={<span>Main</span>}
				sidebar={<span>Sidebar</span>}
				status={<span>Status</span>}
			/>,
		);
		const children = container.querySelectorAll(":scope > div > *");
		const areas = Array.from(children).map(
			(el) => (el as HTMLElement).className,
		);
		expect(areas.some((c) => c.includes("[grid-area:pulse]"))).toBe(true);
		expect(areas.some((c) => c.includes("[grid-area:main]"))).toBe(true);
		expect(areas.some((c) => c.includes("[grid-area:sidebar]"))).toBe(true);
		expect(areas.some((c) => c.includes("[grid-area:status]"))).toBe(true);
	});
});

/* ------------------------------------------------------------------ */
/*  2. AnalyticalLayout                                                */
/* ------------------------------------------------------------------ */

describe("AnalyticalLayout", () => {
	it("renders main children", () => {
		render(<AnalyticalLayout main={<span>Main Content</span>} />);
		expect(screen.getByText("Main Content")).toBeInTheDocument();
	});

	it("renders all slots", () => {
		render(
			<AnalyticalLayout
				strip={<span>Strip</span>}
				main={<span>Main</span>}
				activity={<span>Activity</span>}
				analysis={<span>Analysis</span>}
			/>,
		);
		expect(screen.getByText("Strip")).toBeInTheDocument();
		expect(screen.getByText("Main")).toBeInTheDocument();
		expect(screen.getByText("Activity")).toBeInTheDocument();
		expect(screen.getByText("Analysis")).toBeInTheDocument();
	});

	it("omits optional slots when not provided", () => {
		render(<AnalyticalLayout main={<span>Main</span>} />);
		expect(screen.getByText("Main")).toBeInTheDocument();
		expect(screen.queryByText("Strip")).not.toBeInTheDocument();
		expect(screen.queryByText("Activity")).not.toBeInTheDocument();
		expect(screen.queryByText("Analysis")).not.toBeInTheDocument();
	});

	it("applies grid layout without banner or analysis", () => {
		const { container } = render(
			<AnalyticalLayout main={<span>Main</span>} />,
		);
		const root = expectGridRoot(container);
		expect(root.className).toContain("grid-cols-[1fr_var(--width-activity)]");
		expect(root.className).toContain("grid-rows-[auto_1fr]");
	});

	it("applies grid layout with analysis, no banner", () => {
		const { container } = render(
			<AnalyticalLayout
				main={<span>Main</span>}
				analysis={<span>Analysis</span>}
			/>,
		);
		const root = expectGridRoot(container);
		expect(root.className).toContain(
			"grid-rows-[auto_1fr_var(--height-analysis-band)]",
		);
	});

	it("applies grid layout with banner, no analysis", () => {
		const { container } = render(
			<AnalyticalLayout
				strip={<span>Strip</span>}
				banner={<span>Banner</span>}
				main={<span>Main</span>}
				activity={<span>Activity</span>}
			/>,
		);
		const root = expectGridRoot(container);
		expect(root.className).toContain("grid-rows-[auto_auto_1fr]");
		expect(root.className).toContain(
			'[grid-template-areas:"strip_strip""banner_banner""main_activity"]',
		);
	});

	it("applies grid layout with banner and analysis", () => {
		const { container } = render(
			<AnalyticalLayout
				strip={<span>Strip</span>}
				banner={<span>Banner</span>}
				main={<span>Main</span>}
				activity={<span>Activity</span>}
				analysis={<span>Analysis</span>}
			/>,
		);
		const root = expectGridRoot(container);
		expect(root.className).toContain(
			"grid-rows-[auto_auto_1fr_var(--height-analysis-band)]",
		);
		expect(root.className).toContain(
			'[grid-template-areas:"strip_strip""banner_banner""main_activity""analysis_activity"]',
		);
	});

	it("assigns correct grid-area to each slot", () => {
		const { container } = render(
			<AnalyticalLayout
				strip={<span>Strip</span>}
				main={<span>Main</span>}
				activity={<span>Activity</span>}
				analysis={<span>Analysis</span>}
			/>,
		);
		const children = container.querySelectorAll(":scope > div > *");
		const areas = Array.from(children).map(
			(el) => (el as HTMLElement).className,
		);
		expect(areas.some((c) => c.includes("[grid-area:strip]"))).toBe(true);
		expect(areas.some((c) => c.includes("[grid-area:main]"))).toBe(true);
		expect(areas.some((c) => c.includes("[grid-area:activity]"))).toBe(true);
		expect(areas.some((c) => c.includes("[grid-area:analysis]"))).toBe(true);
	});

	it("assigns banner grid-area when provided", () => {
		const { container } = render(
			<AnalyticalLayout
				banner={<span>Banner</span>}
				main={<span>Main</span>}
			/>,
		);
		const children = container.querySelectorAll(":scope > div > *");
		const areas = Array.from(children).map(
			(el) => (el as HTMLElement).className,
		);
		expect(areas.some((c) => c.includes("[grid-area:banner]"))).toBe(true);
	});
});

/* ------------------------------------------------------------------ */
/*  3. CatalogLayout                                                   */
/* ------------------------------------------------------------------ */

describe("CatalogLayout", () => {
	it("renders main children", () => {
		render(<CatalogLayout main={<span>Main Content</span>} />);
		expect(screen.getByText("Main Content")).toBeInTheDocument();
	});

	it("renders all slots", () => {
		render(
			<CatalogLayout
				toolbar={<span>Toolbar</span>}
				main={<span>Main</span>}
				detail={<span>Detail</span>}
			/>,
		);
		expect(screen.getByText("Toolbar")).toBeInTheDocument();
		expect(screen.getByText("Main")).toBeInTheDocument();
		expect(screen.getByText("Detail")).toBeInTheDocument();
	});

	it("omits optional slots when not provided", () => {
		render(<CatalogLayout main={<span>Main</span>} />);
		expect(screen.getByText("Main")).toBeInTheDocument();
		expect(screen.queryByText("Toolbar")).not.toBeInTheDocument();
		expect(screen.queryByText("Detail")).not.toBeInTheDocument();
	});

	it("applies grid layout classes", () => {
		const { container } = render(
			<CatalogLayout main={<span>Main</span>} />,
		);
		const root = expectGridRoot(container);
		expect(root.className).toContain(
			"grid-cols-[1fr_var(--width-catalog-detail)]",
		);
		expect(root.className).toContain("grid-rows-[auto_1fr]");
	});

	it("assigns correct grid-area to each slot (main maps to table)", () => {
		const { container } = render(
			<CatalogLayout
				toolbar={<span>Toolbar</span>}
				main={<span>Main</span>}
				detail={<span>Detail</span>}
			/>,
		);
		const children = container.querySelectorAll(":scope > div > *");
		const areas = Array.from(children).map(
			(el) => (el as HTMLElement).className,
		);
		expect(areas.some((c) => c.includes("[grid-area:toolbar]"))).toBe(true);
		expect(areas.some((c) => c.includes("[grid-area:main]"))).toBe(true);
		expect(areas.some((c) => c.includes("[grid-area:detail]"))).toBe(true);
	});
});

/* ------------------------------------------------------------------ */
/*  4. ObjectHubLayout                                                 */
/* ------------------------------------------------------------------ */

describe("ObjectHubLayout", () => {
	it("renders main children", () => {
		render(<ObjectHubLayout main={<span>Main Content</span>} />);
		expect(screen.getByText("Main Content")).toBeInTheDocument();
	});

	it("renders all slots", () => {
		render(
			<ObjectHubLayout
				meta={<span>Meta</span>}
				tabs={<span>Tabs</span>}
				main={<span>Main</span>}
				bottom={<span>Bottom</span>}
			/>,
		);
		expect(screen.getByText("Meta")).toBeInTheDocument();
		expect(screen.getByText("Tabs")).toBeInTheDocument();
		expect(screen.getByText("Main")).toBeInTheDocument();
		expect(screen.getByText("Bottom")).toBeInTheDocument();
	});

	it("omits optional slots when not provided", () => {
		render(<ObjectHubLayout main={<span>Main</span>} />);
		expect(screen.getByText("Main")).toBeInTheDocument();
		expect(screen.queryByText("Meta")).not.toBeInTheDocument();
		expect(screen.queryByText("Tabs")).not.toBeInTheDocument();
		expect(screen.queryByText("Bottom")).not.toBeInTheDocument();
	});

	it("applies grid layout classes", () => {
		const { container } = render(
			<ObjectHubLayout main={<span>Main</span>} />,
		);
		const root = expectGridRoot(container);
		expect(root.className).toContain("grid-cols-1");
		expect(root.className).toContain("grid-rows-[auto_auto_1fr_auto]");
	});

	it("assigns correct grid-area to each slot", () => {
		const { container } = render(
			<ObjectHubLayout
				meta={<span>Meta</span>}
				tabs={<span>Tabs</span>}
				main={<span>Main</span>}
				bottom={<span>Bottom</span>}
			/>,
		);
		const children = container.querySelectorAll(":scope > div > *");
		const areas = Array.from(children).map(
			(el) => (el as HTMLElement).className,
		);
		expect(areas.some((c) => c.includes("[grid-area:meta]"))).toBe(true);
		expect(areas.some((c) => c.includes("[grid-area:tabs]"))).toBe(true);
		expect(areas.some((c) => c.includes("[grid-area:main]"))).toBe(true);
		expect(areas.some((c) => c.includes("[grid-area:bottom]"))).toBe(true);
	});
});

/* ------------------------------------------------------------------ */
/*  5. StudioLayout                                                    */
/* ------------------------------------------------------------------ */

describe("StudioLayout", () => {
	it("renders main children", () => {
		render(<StudioLayout main={<span>Main Content</span>} />);
		expect(screen.getByText("Main Content")).toBeInTheDocument();
	});

	it("renders all slots", () => {
		render(
			<StudioLayout
				source={<span>Source</span>}
				main={<span>Main</span>}
				inspector={<span>Inspector</span>}
				logs={<span>Logs</span>}
			/>,
		);
		expect(screen.getByText("Source")).toBeInTheDocument();
		expect(screen.getByText("Main")).toBeInTheDocument();
		expect(screen.getByText("Inspector")).toBeInTheDocument();
		expect(screen.getByText("Logs")).toBeInTheDocument();
	});

	it("omits optional slots when not provided", () => {
		render(<StudioLayout main={<span>Main</span>} />);
		expect(screen.getByText("Main")).toBeInTheDocument();
		expect(screen.queryByText("Source")).not.toBeInTheDocument();
		expect(screen.queryByText("Inspector")).not.toBeInTheDocument();
		expect(screen.queryByText("Logs")).not.toBeInTheDocument();
	});

	it("applies grid layout classes", () => {
		const { container } = render(
			<StudioLayout main={<span>Main</span>} />,
		);
		const root = expectGridRoot(container);
		expect(root.className).toContain(
			"grid-cols-[var(--width-studio-source)_1fr_var(--width-studio-inspector)]",
		);
		expect(root.className).toContain(
			"grid-rows-[auto_1fr_var(--height-status-bar)]",
		);
	});

	it("assigns correct grid-area to each slot", () => {
		const { container } = render(
			<StudioLayout
				source={<span>Source</span>}
				main={<span>Main</span>}
				inspector={<span>Inspector</span>}
				logs={<span>Logs</span>}
			/>,
		);
		const children = container.querySelectorAll(":scope > div > *");
		const areas = Array.from(children).map(
			(el) => (el as HTMLElement).className,
		);
		expect(areas.some((c) => c.includes("[grid-area:sources]"))).toBe(true);
		expect(areas.some((c) => c.includes("[grid-area:main]"))).toBe(true);
		expect(areas.some((c) => c.includes("[grid-area:inspector]"))).toBe(true);
		expect(areas.some((c) => c.includes("[grid-area:logs]"))).toBe(true);
	});
});

/* ------------------------------------------------------------------ */
/*  6. OpsConsoleLayout                                                */
/* ------------------------------------------------------------------ */

describe("OpsConsoleLayout", () => {
	it("renders main children", () => {
		render(<OpsConsoleLayout main={<span>Main Content</span>} />);
		expect(screen.getByText("Main Content")).toBeInTheDocument();
	});

	it("renders all slots", () => {
		render(
			<OpsConsoleLayout
				health={<span>Health</span>}
				main={<span>Main</span>}
				detail={<span>Detail</span>}
			/>,
		);
		expect(screen.getByText("Health")).toBeInTheDocument();
		expect(screen.getByText("Main")).toBeInTheDocument();
		expect(screen.getByText("Detail")).toBeInTheDocument();
	});

	it("omits optional slots when not provided", () => {
		render(<OpsConsoleLayout main={<span>Main</span>} />);
		expect(screen.getByText("Main")).toBeInTheDocument();
		expect(screen.queryByText("Health")).not.toBeInTheDocument();
		expect(screen.queryByText("Detail")).not.toBeInTheDocument();
	});

	it("applies grid layout classes", () => {
		const { container } = render(
			<OpsConsoleLayout main={<span>Main</span>} />,
		);
		const root = expectGridRoot(container);
		expect(root.className).toContain(
			"grid-cols-[1fr_var(--width-ops-detail)]",
		);
		expect(root.className).toContain("grid-rows-[auto_1fr]");
	});

	it("assigns correct grid-area to each slot", () => {
		const { container } = render(
			<OpsConsoleLayout
				health={<span>Health</span>}
				main={<span>Main</span>}
				detail={<span>Detail</span>}
			/>,
		);
		const children = container.querySelectorAll(":scope > div > *");
		const areas = Array.from(children).map(
			(el) => (el as HTMLElement).className,
		);
		expect(areas.some((c) => c.includes("[grid-area:health]"))).toBe(true);
		expect(areas.some((c) => c.includes("[grid-area:main]"))).toBe(true);
		expect(areas.some((c) => c.includes("[grid-area:detail]"))).toBe(true);
	});
});

/* ------------------------------------------------------------------ */
/*  7. RadarLayout                                                     */
/* ------------------------------------------------------------------ */

describe("RadarLayout", () => {
	it("renders main children", () => {
		render(<RadarLayout main={<span>Main Content</span>} />);
		expect(screen.getByText("Main Content")).toBeInTheDocument();
	});

	it("renders all slots", () => {
		render(
			<RadarLayout
				contextBar={<span>ContextBar</span>}
				scopeStrip={<span>ScopeStrip</span>}
				main={<span>Main</span>}
				rightRail={<span>RightRail</span>}
				tabBand={<span>TabBand</span>}
				statusBar={<span>Status</span>}
			/>,
		);
		expect(screen.getByText("ContextBar")).toBeInTheDocument();
		expect(screen.getByText("ScopeStrip")).toBeInTheDocument();
		expect(screen.getByText("Main")).toBeInTheDocument();
		expect(screen.getByText("RightRail")).toBeInTheDocument();
		expect(screen.getByText("TabBand")).toBeInTheDocument();
		expect(screen.getByText("Status")).toBeInTheDocument();
	});

	it("omits optional slots when not provided", () => {
		render(<RadarLayout main={<span>Main</span>} />);
		expect(screen.getByText("Main")).toBeInTheDocument();
		expect(screen.queryByText("ContextBar")).not.toBeInTheDocument();
		expect(screen.queryByText("ScopeStrip")).not.toBeInTheDocument();
		expect(screen.queryByText("RightRail")).not.toBeInTheDocument();
		expect(screen.queryByText("TabBand")).not.toBeInTheDocument();
		expect(screen.queryByText("Status")).not.toBeInTheDocument();
	});

	it("applies flex scroll layout classes", () => {
		const { container } = render(
			<RadarLayout main={<span>Main</span>} />,
		);
		const root = container.firstChild as HTMLElement;
		expect(root.tagName).toBe("DIV");
		expect(root.className).toContain("flex");
		expect(root.className).toContain("h-full");
		expect(root.className).toContain("w-full");
		expect(root.className).toContain("flex-col");
		expect(root.className).toContain("overflow-y-auto");
	});

	it("applies workspace grid with activity width column", () => {
		const { container } = render(
			<RadarLayout
				main={<span>Main</span>}
				rightRail={<span>Rail</span>}
			/>,
		);
		const root = container.firstChild as HTMLElement;
		const workspace = root.querySelector("[data-slot='main']")
			?.parentElement;
		expect(workspace).toBeTruthy();
		expect(workspace?.className).toContain("grid");
		expect(workspace?.className).toContain(
			"grid-cols-[1fr_var(--width-activity)]",
		);
	});

	it("applies sticky top-0 to context-bar", () => {
		const { container } = render(
			<RadarLayout
				contextBar={<span>Ctx</span>}
				main={<span>Main</span>}
			/>,
		);
		const contextBar = container.querySelector(
			"[data-slot='context-bar']",
		);
		expect(contextBar).toBeTruthy();
		expect(contextBar?.className).toContain("sticky");
		expect(contextBar?.className).toContain("top-0");
		expect(contextBar?.className).toContain("z-15");
	});

	it("applies sticky offsets with context bar present", () => {
		const { container } = render(
			<RadarLayout
				contextBar={<span>Ctx</span>}
				scopeStrip={<span>Scope</span>}
				main={<span>Main</span>}
				rightRail={<span>Rail</span>}
			/>,
		);
		const scopeStrip = container.querySelector(
			"[data-slot='scope-strip']",
		);
		expect(scopeStrip?.className).toContain("sticky");
		expect(scopeStrip?.className).toContain("top-8");

		const rightRail = container.querySelector(
			"[data-slot='right-rail']",
		);
		expect(rightRail?.className).toContain("sticky");
		expect(rightRail?.className).toContain("top-8");
		expect(rightRail?.className).toContain("self-start");
	});

	it("applies sticky top-0 when context bar absent", () => {
		const { container } = render(
			<RadarLayout
				scopeStrip={<span>Scope</span>}
				main={<span>Main</span>}
				rightRail={<span>Rail</span>}
			/>,
		);
		const scopeStrip = container.querySelector(
			"[data-slot='scope-strip']",
		);
		expect(scopeStrip?.className).toContain("sticky");
		expect(scopeStrip?.className).toContain("top-0");

		const rightRail = container.querySelector(
			"[data-slot='right-rail']",
		);
		expect(rightRail?.className).toContain("sticky");
		expect(rightRail?.className).toContain("top-0");
	});

	it("assigns correct data-slot attributes", () => {
		const { container } = render(
			<RadarLayout
				contextBar={<span>Ctx</span>}
				scopeStrip={<span>Scope</span>}
				main={<span>Main</span>}
				rightRail={<span>Rail</span>}
				tabBand={<span>Tabs</span>}
				statusBar={<span>Status</span>}
			/>,
		);
		expect(
			container.querySelector("[data-slot='context-bar']"),
		).toBeTruthy();
		expect(
			container.querySelector("[data-slot='scope-strip']"),
		).toBeTruthy();
		expect(
			container.querySelector("[data-slot='main']"),
		).toBeTruthy();
		expect(
			container.querySelector("[data-slot='right-rail']"),
		).toBeTruthy();
		expect(
			container.querySelector("[data-slot='tab-band']"),
		).toBeTruthy();
		expect(
			container.querySelector("[data-slot='status-bar']"),
		).toBeTruthy();
	});
});
