#!/usr/bin/env bun

import { Generator, getConfig } from "@tanstack/router-generator";

const root = process.cwd();
const config = getConfig({ quoteStyle: "double", semicolons: true }, root);
await new Generator({ config, root }).run();
