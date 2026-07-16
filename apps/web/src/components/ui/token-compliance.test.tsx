import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { badgeVariants } from "./badge";
import { buttonVariants } from "./button";
import { tabsListVariants } from "./tabs";

const UI_ROOT = join(process.cwd(), "src/components/ui");

const PRIMITIVE_FILES = [
	"button.tsx",
	"badge.tsx",
	"tabs.tsx",
	"dialog.tsx",
	"sheet.tsx",
] as const;

const SHADCN_DEFAULT_TOKENS = [
	"bg-primary",
	"text-primary",
	"text-primary-foreground",
	"ring-ring",
	"border-ring",
	"outline-ring",
	"border-border",
	"bg-background",
	"bg-muted",
	"text-muted-foreground",
	"bg-secondary",
	"text-secondary",
	"bg-destructive",
	"text-destructive",
	"border-destructive",
	"ring-destructive",
	"border-input",
	"bg-input",
] as const;

function readUiSource(fileName: string): string {
	return readFileSync(join(UI_ROOT, fileName), "utf-8");
}

describe("core UI primitive token compliance", () => {
	it("keeps Button, Badge, Tabs, Dialog, and Sheet off shadcn default tokens", () => {
		const violations: string[] = [];

		for (const fileName of PRIMITIVE_FILES) {
			const source = readUiSource(fileName);

			for (const token of SHADCN_DEFAULT_TOKENS) {
				if (source.includes(token)) {
					violations.push(`${fileName}: ${token}`);
				}
			}
		}

		expect(violations.join("\n")).toBe("");
	});

	it("keeps cva primitive variants on Ditto semantic tokens", () => {
		expect(buttonVariants()).toContain("bg-(--color-accent)");
		expect(buttonVariants({ variant: "outline" })).toContain(
			"border-(--color-border-default)",
		);
		expect(badgeVariants()).toContain("bg-(--color-accent)");
		expect(tabsListVariants()).toContain("bg-(--color-surface-muted)");
	});
});
