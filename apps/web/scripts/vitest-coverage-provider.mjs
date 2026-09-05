// Vitest resolves built-in provider package names from its physical install path.
// Under Bun's isolated linker that path cannot see workspace-level optional tools,
// so load the exact same provider from the Web workspace boundary instead.
export { default } from "@vitest/coverage-v8";
