import { afterEach, describe, expect, test } from "bun:test";
import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

import { compareTrees } from "../sync-skills.mjs";
import { parseFrontmatter, validateRepository } from "../validate.mjs";

const temporaryDirectories = [];

afterEach(async () => {
	await Promise.all(temporaryDirectories.splice(0).map((directory) => rm(directory, { recursive: true, force: true })));
});

test("skill mirror detects missing files and drift", async () => {
	const root = await mkdtemp(path.join(tmpdir(), "ditto-app-skills-"));
	temporaryDirectories.push(root);
	const source = path.join(root, "source");
	const mirror = path.join(root, "mirror");
	await mkdir(source);
	await mkdir(mirror);
	await writeFile(path.join(source, "SKILL.md"), "canonical\n");

	expect(await compareTrees(source, mirror)).toEqual(["missing from Claude mirror: SKILL.md"]);
	await writeFile(path.join(mirror, "SKILL.md"), "drift\n");
	expect(await compareTrees(source, mirror)).toEqual(["content drift: SKILL.md"]);
});

test("frontmatter accepts only name and description", () => {
	expect(parseFrontmatter("---\nname: sample\ndescription: sample trigger\n---\n\n# Sample\n")).toEqual({
		name: "sample",
		description: "sample trigger",
	});
	expect(() => parseFrontmatter("---\nname: sample\ndescription: trigger\nextra: no\n---\n")).toThrow();
});

describe("repository harness", () => {
	test("passes its own static contract", async () => {
		expect(await validateRepository(path.resolve(import.meta.dir, "../../.."))).toEqual([]);
	});
});
