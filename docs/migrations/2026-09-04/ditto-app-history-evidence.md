# Ditto App history migration evidence

Captured at `2026-09-04T09:52:13Z`. All generated artifacts in this directory were produced outside both source repositories. The source `ditto-app` repository and the backend repository were not modified by this task.

## Source repository

- Path: `/Users/chevy/Desktop/code/ditto-app`
- Symbolic HEAD: `refs/heads/main`
- HEAD: `ee8c701b1218213004af6b440ccd71df97803e88`
- HEAD tree: `593d5ff79c418c42119af0ad453890d05fcbf4df`
- Commit count, `main`: `557`
- Commit count, `--all`: `557`
- Remote fetch/push: `git@github.com:cosmos-arc/ditto-app.git`
- Source working tree at capture: no tracked changes; pre-existing untracked `pnpm-workspace.yaml` and `tmp/` are intentionally not part of Git history or the bundle.

The all-refs bundle contains 14 advertised refs:

| Ref | Object type | Object ID |
|---|---|---|
| `HEAD` | commit | `ee8c701b1218213004af6b440ccd71df97803e88` |
| `refs/heads/main` | commit | `ee8c701b1218213004af6b440ccd71df97803e88` |
| `refs/heads/codex/roadmap-completion` | commit | `8764b653895cc190efdba1457f02027ce052cf17` |
| `refs/remotes/origin/HEAD` | commit | `ee8c701b1218213004af6b440ccd71df97803e88` |
| `refs/remotes/origin/main` | commit | `ee8c701b1218213004af6b440ccd71df97803e88` |
| `refs/remotes/origin/agent/frontend-quality-convergence` | commit | `419867409ffcfc861b1c52db97c67bed61be0f97` |
| `refs/remotes/origin/codex/r2-data-product-design` | commit | `2593269743f2e07b7817e75724339059e0d95ebd` |
| `refs/remotes/origin/codex/roadmap-completion` | commit | `8764b653895cc190efdba1457f02027ce052cf17` |
| `refs/remotes/origin/feat/prototype-three-zone-architecture` | commit | `2f6f08d94522a3162f3c10dfa1f26bb0ef087bf0` |
| `refs/remotes/origin/feat/r3-research-wiring` | commit | `c436dea24b8a17d1c143e1ee79f44ccbb0267dce` |
| `refs/remotes/origin/feat/wave1-backend-wiring` | commit | `c4d0170bdc19daa815debf37f75711581df9a8a4` |
| `refs/remotes/origin/feature/r1-trading-live` | commit | `5814cddf676e3fafca28e391132c36ee3420961a` |
| `refs/codex/turn-diffs/checkpoints/b38004416f15951f75ddb9f3d02e61fddb80ba13aed5155e91d193b03c6dccd4/684cd517938dbab0a0e6c9c68c91a9e1c760f704aae4c19cc30caa5507342888/1787196949874/ed29c3f2-9f8c-4d61-932d-fa598c3da7e6` | tree | `60f16c7b173b74bf06a66553288c48af840259ea` |
| `refs/codex/turn-diffs/checkpoints/c1d590b104d382632bf9f792b449d4019578d178f096072b14de6a25ad12617e/7da67c0f5bd9c406f8a4e00798a69dc6e23d77dcb3d566257488d2a390719557/1787657766502/1e59a7c4-af0e-4e63-8ff4-5688d58a37be` | tree | `db9bbd5efa4912c5c16386888c57d7b3e5783753` |

The two non-commit Codex checkpoint refs are preserved in the original bundle but were excluded from history rewriting. The 11 advertised commit refs reduce to eight unique branch names/tips after local/remote duplicates are normalized by the mirror/filter operation.

## Tool provenance

- Project: official `newren/git-filter-repo`
- Source: `https://github.com/newren/git-filter-repo.git`
- Fixed tag: `v2.47.0`
- Tag object: `cbad6503f5de690c9d5a376d900136691c330793`
- Peeled source commit: `6f79afc8c90c592a3052e6cc53c2ca8907515bca`
- `git-filter-repo --version`: `a40bce548d2c`
- Script Git blob: `a40bce548d2c0bd0b8d5e233e8930d462e35e495`
- Script SHA-256: `67447413e273fc76809289111748870b6f6072f08b17efe94863a92d810b7d94`

The official tag is annotated with `filter-repo v2.47.0` and points to the peeled source commit above.

## Filter operation

The isolated bare mirror was cloned from `bundles/ditto-app-all-refs.bundle`; no source working tree was used as the filter target. The fixed tool was run with:

```text
--to-subdirectory-filter apps/web --force
```

Filtered repository:

`/Users/chevy/Desktop/code/ditto-monorepo-migration-20260904/frontend-evidence/work/ditto-app-filtered.git`

Filtered `main`:

- Commit: `175743a4a63cbc78aa9d9a761b90aae544092991`
- Root tree: `d3f7ed40ed3c2f9e695ea889cf7a5d30da70b0ef`
- `apps/web` subtree: `593d5ff79c418c42119af0ad453890d05fcbf4df`
- Commit count: `557`

The `apps/web` subtree object is exactly the original `main` tree object, proving path, mode, symlink and blob-byte equivalence for the full tip tree.

## Verification

- Original bundle: `git bundle verify` passed and reports complete SHA-1 history.
- Filtered bundle: `git bundle verify` passed and reports complete SHA-1 history.
- Filtered bare repository: `git fsck --full --strict` passed.
- `commit-map`: 557 old/new commit mappings plus one header; zero commits filtered out.
- For all 557 mappings, old tree equals new `apps/web` subtree: zero mismatches.
- For all 557 mappings, author name/email/time and committer name/email/time: zero mismatches.
- Main/all commit counts: `557 → 557`.
- Author-date range preserved: `2026-03-25T20:46:39+08:00` through `2026-09-04T16:46:00+08:00`.
- Unique author identity count preserved: `3 → 3`.
- Commit messages: 556 byte-identical; one was intentionally rewritten by git-filter-repo to replace the old short commit reference `9a9e143` with mapped short SHA `f0cfdf4` in old/new commit `87aa518... → 9542bc4...`.
- `filter-repo/suboptimal-issues` records one pre-existing reference to filtered-out commit hash `dae9ec54`; the reference remains text in a commit message and is not a graph-integrity error.

## Suggested archive refs for the eventual monorepo

Do not push the isolated filtered repository back to the old frontend remote. For the eventual import:

1. Preserve the original all-refs bundle plus its SHA-256 as the authoritative unmodified archive.
2. Expose filtered `main` temporarily as `refs/heads/import/ditto-app-main` for the unrelated-history merge.
3. Before the merge, retain `175743a4...` as an annotated archive tag such as `archive/ditto-app-filtered-main-20260904`.
4. If non-main branch tips must remain browsable, rename them under `refs/heads/archive/ditto-app/...` or create annotated archive tags; do not leave their generic names in the monorepo branch namespace.
5. Keep the two Codex checkpoint tree refs only in the original bundle; they are editor state, not product history.

No merge into the backend repository was performed.
