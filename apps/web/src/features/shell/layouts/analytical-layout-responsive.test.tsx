import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AnalyticalLayout } from "./analytical.layout";

describe("AnalyticalLayout responsive activity rail", () => {
	it("stacks the activity rail below the main workspace on narrow screens", () => {
		const { container } = render(
			<AnalyticalLayout
				strip={<span>Strip</span>}
				banner={<span>Banner</span>}
				main={<span>Main</span>}
				activity={<span>Activity</span>}
			/>,
		);

		const root = container.firstElementChild;
		const main = container.querySelector("[data-slot='main']");
		const activity = container.querySelector("[data-slot='activity']");

		expect(root?.className).toContain("max-md:grid-cols-[minmax(0,1fr)]");
		expect(root?.className).toContain('max-md:[grid-template-areas:"strip""banner""main""activity"]');
		expect(main?.className).toContain("max-md:overflow-y-auto");
		expect(activity?.className).toContain("max-md:max-h-56");
		expect(activity?.className).toContain("max-md:overflow-y-auto");
	});
});
