import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { OverlayProvider, useOverlayController } from "./overlay-provider";

function OverlayHarness() {
	const { activeOverlayId, closeOverlay, openOverlay } = useOverlayController();

	return (
		<div>
			<p>active:{activeOverlayId ?? "none"}</p>
			<button type="button" onClick={() => openOverlay("orders.detail")}>
				open
			</button>
			<button type="button" onClick={closeOverlay}>
				close
			</button>
		</div>
	);
}

describe("OverlayProvider", () => {
	it("opens and closes overlays by id", async () => {
		const user = userEvent.setup();
		render(
			<OverlayProvider>
				<OverlayHarness />
			</OverlayProvider>,
		);

		expect(screen.getByText("active:none")).toBeInTheDocument();

		await user.click(screen.getByRole("button", { name: "open" }));
		expect(screen.getByText("active:orders.detail")).toBeInTheDocument();

		await user.click(screen.getByRole("button", { name: "close" }));
		expect(screen.getByText("active:none")).toBeInTheDocument();
	});
});
