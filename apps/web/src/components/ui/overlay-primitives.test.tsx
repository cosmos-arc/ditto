import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { sheetVariants } from "./sheet";

const UI_ROOT = join(process.cwd(), "src/components/ui");
const DRAWER_PATH = join(process.cwd(), "src/components/indicator/overlay/drawer.tsx");

function readUiSource(fileName: string): string {
	return readFileSync(join(UI_ROOT, fileName), "utf-8");
}

describe("overlay primitives", () => {
	it("use Ditto overlay surface tokens instead of raw black backdrops", () => {
		expect(readUiSource("dialog.tsx")).not.toContain("bg-black/50");
		expect(readUiSource("sheet.tsx")).not.toContain("bg-black/50");
		expect(readUiSource("dialog.tsx")).toContain("bg-(--color-surface-overlay)");
		expect(readUiSource("sheet.tsx")).toContain("bg-(--color-surface-overlay)");
	});

	it("render semantic close buttons without entity glyphs", () => {
		expect(readUiSource("dialog.tsx")).not.toContain("&times;");
		expect(readUiSource("sheet.tsx")).not.toContain("&times;");
		expect(readUiSource("dialog.tsx")).toContain('aria-label="Close"');
		expect(readUiSource("sheet.tsx")).toContain('aria-label="Close"');
	});

	it("keeps sheet right side viewport-safe before applying the drawer width token", () => {
		const classes = sheetVariants({ side: "right" });
		expect(classes).toContain("w-full");
		expect(classes).toContain("max-w-full");
		expect(classes).toContain("sm:w-(--width-drawer)");
		expect(classes).toContain("sm:max-w-(--width-drawer)");
	});

	it("keeps Drawer viewport-safe and bound to the shared desktop width token", () => {
		const source = readFileSync(DRAWER_PATH, "utf-8");
		expect(source).toContain("w-full max-w-full");
		expect(source).toContain("sm:w-(--width-drawer) sm:max-w-(--width-drawer)");
	});
});
