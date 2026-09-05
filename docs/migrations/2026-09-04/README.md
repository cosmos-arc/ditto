# Ditto polyglot monorepo migration record

This directory is the tracked audit index for the 2026-09-04 import of
`cosmos-arc/ditto-app` into `apps/web`. Large recovery artifacts remain outside
Git and are identified by SHA-256 below.

## Frozen inputs

| Repository | Canonical ref | Commit | Tree | Commit count |
|---|---|---|---|---:|
| `cosmos-arc/ditto` | `main` | `0b0b61f17df972989de79e212fc1982f05388495` | `094b01655c9c14dc3ed7af0e8ab42d39a4f1ad12` | 193 |
| `cosmos-arc/ditto-app` | `main` | `ee8c701b1218213004af6b440ccd71df97803e88` | `593d5ff79c418c42119af0ad453890d05fcbf4df` | 557 |

The frontend source had no tracked changes. Its pre-existing untracked
`pnpm-workspace.yaml` and `tmp/` were deliberately excluded from the bundle,
filter operation, and monorepo tree. The original repository was not edited.

## Recovery artifacts

Local recovery root at capture time:

```text
/Users/chevy/Desktop/code/ditto-monorepo-migration-20260904/
```

| Artifact | SHA-256 |
|---|---|
| `backend-evidence/ditto-all-refs.bundle` | `fcfc77334b8170f259fff5e7be0c078460b8b3f1b6b360f9e42f68001ec46809` |
| `frontend-evidence/bundles/ditto-app-all-refs.bundle` | `10550d1fc707b6ceecfb7a7b182dd061b35a20bbd06d7801a36a159966bd818a` |
| `frontend-evidence/bundles/ditto-app-filtered-apps-web.bundle` | `3c57d291f1cf9af0540025e1187bed6820932abf0e59bbab00d53ad3a28be90d` |
| `frontend-evidence/tooling/git-filter-repo-v2.47.0/git-filter-repo` | `67447413e273fc76809289111748870b6f6072f08b17efe94863a92d810b7d94` |

`github-metadata/` contains repository settings, branches, issues, pull
requests, releases, ruleset responses, branch-protection responses and its own
verified `CHECKSUMS.sha256`. The private-repository ruleset endpoints returned
the GitHub plan limitation response; that failure is retained as evidence.

## Rewrite provenance

- Tool: official `newren/git-filter-repo` tag `v2.47.0`.
- Tag peeled commit: `6f79afc8c90c592a3052e6cc53c2ca8907515bca`.
- Operation: `--to-subdirectory-filter apps/web --force` against an isolated
  bare clone restored from the original bundle.
- Filtered frontend main: `175743a4a63cbc78aa9d9a761b90aae544092991`.
- Monorepo merge commit: `3d2e44b5c66c6b5a669d76da748e72331abfedd7`.
- Annotated local archive tag:
  `archive/ditto-app-filtered-main-20260904`.

The complete per-commit mapping is in
[`ditto-app-commit-map.tsv`](ditto-app-commit-map.tsv); imported branch tips are
in [`ditto-app-ref-map.tsv`](ditto-app-ref-map.tsv). Detailed pre-import evidence
is in [`ditto-app-history-evidence.md`](ditto-app-history-evidence.md).

## Verified invariants

- All 557 frontend commits have an old-to-new mapping; none were filtered out.
- Every mapped commit preserves author identity/time and committer identity/time.
- For every mapped commit, the original root tree equals the rewritten
  `apps/web` subtree.
- The source and filtered `main` histories both contain 557 commits.
- The imported `apps/web` tree is
  `593d5ff79c418c42119af0ad453890d05fcbf4df`, byte-identical to the original
  frontend main tree.
- Both bundles pass `git bundle verify`; the filtered bare repository passes
  `git fsck --full --strict`.
- Backend commit `0b0b61f1` remains an unchanged ancestor of the monorepo.

## Imported branch namespace

The eight rewritten frontend branch tips were retained locally below
`refs/heads/archive/ditto-app/*`. They must be pushed using an explicit refspec
when the migration branch is published; generic frontend branch names must not
be introduced into the canonical namespace.

## Remaining external transition

Do not archive `cosmos-arc/ditto-app` until the root CI gate, contract chain,
system E2E, artifact smoke tests and recovery checks are green on the final
monorepo commit. Repository protection also remains incomplete until the GitHub
plan supports required checks/rulesets.
