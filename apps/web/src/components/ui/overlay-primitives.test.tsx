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

	it("keeps sheet right side compatible with the drawer width token", () => {
		const classes = sheetVariants({ side: "right" });
		expect(classes).toContain("w-(--width-drawer)");
	});

	it("keeps Drawer bound to the shared drawer width token", () => {
		const source = readFileSync(DRAWER_PATH, "utf-8");
		expect(source).toContain("w-(--width-drawer)");
		expect(source).toContain("max-w-(--width-drawer)");
	});
});
