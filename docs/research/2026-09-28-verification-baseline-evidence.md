# 验证基线证据附录

对应[诊断正文](2026-09-28-verification-baseline.md)。固定 SHA `2b928893fdd17141bcc1a625c89265ae0dbb875c`；所有秒数为观测值，非性能承诺。原始日志留本机，附录只保留不含私密会话/配置的可复核摘要。

## 环境

```json
{
  "sha": "2b928893fdd17141bcc1a625c89265ae0dbb875c",
  "platform": "macOS-26.6.2-arm64-arm-64bit-Mach-O",
  "python": "3.13.14",
  "tools": {
    "pytest": "9.1.1",
    "pytest-xdist": "3.8.0",
    "pytest-cov": "7.1.0",
    "pytest-timeout": "2.4.0",
    "basedpyright": "1.39.9",
    "ruff": "0.15.11",
    "polars": "1.43.2",
    "pre-commit": "4.6.1"
  },
  "cpu_count": "8",
  "memory_bytes": "17179869184"
}
```

## 远端样本全集

日期时间均 UTC。wall 是创建到最后非 skipped job 结束；job-sum 是所有 job interval 之和；union 是它们的时间区间并集，不重复计算并行重叠。wall-union 包含无 job 运行的排队/调度空隙，不是完整 runner 排队总和。

| run | event / result | API source SHA | created | wall / job-sum / union (s) |
|---|---|---|---|---:|
| [36354484049](https://github.com/cosmos-arc/ditto/actions/runs/36354484049) | pull_request / success | `46e0e90cd226699f5378c711fdfe7da97cfee99b` | 2026-09-27T22:12:41Z | 1053 / 6393 / 1048 |
| [36352766776](https://github.com/cosmos-arc/ditto/actions/runs/36352766776) | pull_request / failure | `69dfafc0056439a4ffa820a085889a261bc7a929` | 2026-09-27T21:43:27Z | 944 / 6183 / 939 |
| [36352736583](https://github.com/cosmos-arc/ditto/actions/runs/36352736583) | push / success | `840601d005fcbc30d2845cbe543dd0357ac3a45d` | 2026-09-27T21:42:55Z | 446 / 1146 / 440 |
| [36347752794](https://github.com/cosmos-arc/ditto/actions/runs/36347752794) | pull_request / success | `6983ce1721ed5b7e4fc8defe892e3fde7dd453b2` | 2026-09-27T20:21:51Z | 881 / 5999 / 874 |
| [36346509736](https://github.com/cosmos-arc/ditto/actions/runs/36346509736) | pull_request / failure | `61894877050f36652a7b8a010ac6735768fd8e72` | 2026-09-27T20:01:59Z | 895 / 6126 / 792 |
| [36342804075](https://github.com/cosmos-arc/ditto/actions/runs/36342804075) | pull_request / failure | `e996814731d78546eebbb991dd47b615c4604a9f` | 2026-09-27T19:01:26Z | 862 / 6245 / 856 |
| [36340779974](https://github.com/cosmos-arc/ditto/actions/runs/36340779974) | pull_request / failure | `d18b2e92d197d9a755cc6fe73c47990f307fcf9b` | 2026-09-27T18:28:34Z | 846 / 6244 / 840 |
| [36338348194](https://github.com/cosmos-arc/ditto/actions/runs/36338348194) | pull_request / failure | `3fadf8a0f90b9076ae26ac0165e30ae2bccf067b` | 2026-09-27T17:49:11Z | 797 / 5980 / 789 |
| [36337157132](https://github.com/cosmos-arc/ditto/actions/runs/36337157132) | pull_request / failure | `c5730e734c0e480763c85270c5523372920e8615` | 2026-09-27T17:29:56Z | 847 / 6090 / 839 |
| [36335284882](https://github.com/cosmos-arc/ditto/actions/runs/36335284882) | pull_request / failure | `a0680ae821bed677dab4498e5d7feb1d96c87aac` | 2026-09-27T17:00:07Z | 873 / 5790 / 866 |
| [36333399219](https://github.com/cosmos-arc/ditto/actions/runs/36333399219) | pull_request / failure | `bf01151c49ba7ec430730be525ce53934594c873` | 2026-09-27T16:28:58Z | 817 / 5760 / 808 |
| [36332034080](https://github.com/cosmos-arc/ditto/actions/runs/36332034080) | pull_request / failure | `9bf52dcd3ac8665b9a214b7b2f4619a52d6f4ea1` | 2026-09-27T16:07:02Z | 818 / 6004 / 811 |
| [36346232762](https://github.com/cosmos-arc/ditto/actions/runs/36346232762) | pull_request / cancelled | `753d8866527fb7e3ae648203f444455fa5147eb4` | 2026-09-27T19:57:31Z | 362 / 4366 / 355 |
| [36320621684](https://github.com/cosmos-arc/ditto/actions/runs/36320621684) | pull_request / cancelled | `ddd20653797c70b11b5874be1de8ae4a62fead02` | 2026-09-27T12:55:36Z | 816 / 3924 / 739 |
| [36286620839](https://github.com/cosmos-arc/ditto/actions/runs/36286620839) | push / cancelled | `9b4ad6560511c94c06628abef8d85e02dfdd35c2` | 2026-09-27T01:47:56Z | 300 / 953 / 264 |
| [36263338013](https://github.com/cosmos-arc/ditto/actions/runs/36263338013) | pull_request / cancelled | `0347a9479fd568583b636971cae15f38ac99bf29` | 2026-09-26T18:39:53Z | 696 / 5575 / 689 |
| [36357148934](https://github.com/cosmos-arc/ditto/actions/runs/36357148934) | push / success | `2b928893fdd17141bcc1a625c89265ae0dbb875c` | 2026-09-27T22:59:28Z | 705 / 1487 / 698 |

## 最新成功 PR 的关键 job 时间

| job | started UTC | completed UTC | interval (s) | 主要 step 秒数 |
|---|---|---|---:|---|
| [Repository policy](https://github.com/cosmos-arc/ditto/actions/runs/36354484049/job/108719349902) | 2026-09-27T22:12:43Z | 2026-09-27T22:12:58Z | 15 |  |
| [OpenAPI compatibility and generated types](https://github.com/cosmos-arc/ditto/actions/runs/36354484049/job/108719396709) | 2026-09-27T22:13:00Z | 2026-09-27T22:14:10Z | 70 | Run ./.github/actions/setup-toolchain: 22; Contract gate: 37 |
| [Skill structure and mirrors](https://github.com/cosmos-arc/ditto/actions/runs/36354484049/job/108719396711) | 2026-09-27T22:13:00Z | 2026-09-27T22:13:26Z | 26 | Run ./.github/actions/setup-toolchain: 17 |
| [Backend types](https://github.com/cosmos-arc/ditto/actions/runs/36354484049/job/108719396735) | 2026-09-27T22:13:00Z | 2026-09-27T22:13:58Z | 58 | Run ./.github/actions/setup-toolchain: 20; Strict type check: 30 |
| [backend-capacity](https://github.com/cosmos-arc/ditto/actions/runs/36354484049/job/108719396742) | 2026-09-27T22:13:00Z | 2026-09-27T22:16:32Z | 212 | Run ./.github/actions/setup-toolchain: 21; Run scheduler-capacity slow lane: 178 |
| [Backend format and lint](https://github.com/cosmos-arc/ditto/actions/runs/36354484049/job/108719396745) | 2026-09-27T22:13:00Z | 2026-09-27T22:13:37Z | 37 | Run ./.github/actions/setup-toolchain: 22 |
| [Architecture and agent harness](https://github.com/cosmos-arc/ditto/actions/runs/36354484049/job/108719396766) | 2026-09-27T22:13:00Z | 2026-09-27T22:16:11Z | 191 | Run ./.github/actions/setup-toolchain: 24; Architecture boundaries: 24; Agent harness: 130 |
| [Platform smoke (windows-x64)](https://github.com/cosmos-arc/ditto/actions/runs/36354484049/job/108719396773) | 2026-09-27T22:13:00Z | 2026-09-27T22:18:06Z | 306 | Run ./.github/actions/setup-toolchain: 102; Native wheel behavior: 17; Windows backend type gate: 57; Windows Web type gate: 43; Windows backend core unit: 43; Windows loopback API smoke: 19 |
| [Release policy](https://github.com/cosmos-arc/ditto/actions/runs/36354484049/job/108719396780) | 2026-09-27T22:13:00Z | 2026-09-27T22:13:30Z | 30 | Run ./.github/actions/setup-toolchain: 18 |
| [web-build](https://github.com/cosmos-arc/ditto/actions/runs/36354484049/job/108719396790) | 2026-09-27T22:13:00Z | 2026-09-27T22:14:11Z | 71 | Run ./.github/actions/setup-toolchain: 19; Build production Web: 42 |
| [Web static checks and coverage](https://github.com/cosmos-arc/ditto/actions/runs/36354484049/job/108719396793) | 2026-09-27T22:13:00Z | 2026-09-27T22:17:50Z | 290 | Web CI: 265 |
| [backend-shards (0)](https://github.com/cosmos-arc/ditto/actions/runs/36354484049/job/108719396798) | 2026-09-27T22:13:00Z | 2026-09-27T22:21:38Z | 518 | Run ./.github/actions/setup-toolchain: 17; Run isolated shard: 491 |
| [backend-shards (1)](https://github.com/cosmos-arc/ditto/actions/runs/36354484049/job/108719396805) | 2026-09-27T22:13:00Z | 2026-09-27T22:21:04Z | 484 | Run ./.github/actions/setup-toolchain: 20; Run isolated shard: 452 |
| [backend-shards (5)](https://github.com/cosmos-arc/ditto/actions/runs/36354484049/job/108719396808) | 2026-09-27T22:13:00Z | 2026-09-27T22:21:06Z | 486 | Run ./.github/actions/setup-toolchain: 22; Run isolated shard: 452 |
| [web-prototype](https://github.com/cosmos-arc/ditto/actions/runs/36354484049/job/108719396822) | 2026-09-27T22:13:00Z | 2026-09-27T22:16:04Z | 184 | Run ./.github/actions/setup-toolchain: 15; Prepare browser: 15; Prototype coverage of product flows: 143 |
| [backend-shards (3)](https://github.com/cosmos-arc/ditto/actions/runs/36354484049/job/108719396852) | 2026-09-27T22:13:00Z | 2026-09-27T22:20:32Z | 452 | Run ./.github/actions/setup-toolchain: 18; Run isolated shard: 425 |
| [backend-shards (2)](https://github.com/cosmos-arc/ditto/actions/runs/36354484049/job/108719396856) | 2026-09-27T22:13:00Z | 2026-09-27T22:19:56Z | 416 | Run ./.github/actions/setup-toolchain: 16; Run isolated shard: 391 |
| [Platform smoke (macos-arm64)](https://github.com/cosmos-arc/ditto/actions/runs/36354484049/job/108719396907) | 2026-09-27T22:13:33Z | 2026-09-27T22:24:31Z | 658 | Run ./.github/actions/setup-toolchain: 30; macOS backend gate: 314; macOS Web gate: 290 |
| [backend-shards (4)](https://github.com/cosmos-arc/ditto/actions/runs/36354484049/job/108719396911) | 2026-09-27T22:13:32Z | 2026-09-27T22:22:16Z | 524 | Run ./.github/actions/setup-toolchain: 21; Run isolated shard: 490 |
| [Security and supply chain / Secret history scan](https://github.com/cosmos-arc/ditto/actions/runs/36354484049/job/108719397128) | 2026-09-27T22:13:23Z | 2026-09-27T22:14:20Z | 57 | Gitleaks full-history scan: 45 |
| [Security and supply chain / CodeQL (actions)](https://github.com/cosmos-arc/ditto/actions/runs/36354484049/job/108719397137) | 2026-09-27T22:13:00Z | 2026-09-27T22:13:45Z | 45 | Analyze locally: 17 |
| [Security and supply chain / OSV lockfile scan](https://github.com/cosmos-arc/ditto/actions/runs/36354484049/job/108719397142) | 2026-09-27T22:13:00Z | 2026-09-27T22:13:21Z | 21 |  |
| [Security and supply chain / CodeQL (python)](https://github.com/cosmos-arc/ditto/actions/runs/36354484049/job/108719397146) | 2026-09-27T22:13:00Z | 2026-09-27T22:16:40Z | 220 | Analyze locally: 192 |
| [Security and supply chain / CodeQL (javascript-typescript)](https://github.com/cosmos-arc/ditto/actions/runs/36354484049/job/108719397172) | 2026-09-27T22:13:00Z | 2026-09-27T22:14:14Z | 74 | Initialize CodeQL: 15; Analyze locally: 40 |
| [Supervised backend-Web system test](https://github.com/cosmos-arc/ditto/actions/runs/36354484049/job/108719606081) | 2026-09-27T22:14:49Z | 2026-09-27T22:20:19Z | 330 | Run ./.github/actions/setup-toolchain: 20; Run supervised system test: 284 |
| [Container build and readiness smoke](https://github.com/cosmos-arc/ditto/actions/runs/36354484049/job/108719606137) | 2026-09-27T22:14:13Z | 2026-09-27T22:16:34Z | 141 | Run ./.github/actions/setup-toolchain: 19; Build once, scan, attest subject and smoke: 91; Upload artifact evidence: 23 |
| [Security and supply chain / Security gate](https://github.com/cosmos-arc/ditto/actions/runs/36354484049/job/108720048958) | 2026-09-27T22:16:42Z | 2026-09-27T22:16:45Z | 3 |  |
| [Backend tests and coverage](https://github.com/cosmos-arc/ditto/actions/runs/36354484049/job/108721014291) | 2026-09-27T22:22:19Z | 2026-09-27T22:30:10Z | 471 | Run ./.github/actions/setup-toolchain: 37; Verify shard completeness and coverage floor: 31; New test duration gate: 205; PIT correctness suite: 171 |
| [CI gate](https://github.com/cosmos-arc/ditto/actions/runs/36354484049/job/108722314896) | 2026-09-27T22:30:11Z | 2026-09-27T22:30:14Z | 3 |  |

## 本地 task check 顺序边界

由 stdout 中 `task: [...]` 到达时间记录；相邻差包含进程/调度/输出开销，不等同 profiler 独占耗时。

| 命令 | start offset (s) | 到下一边界或进程结束 (s) |
|---|---:|---:|
| `task: [toolchain-check] "/Users/chevy/Desktop/code/ditto/.venv/bin/python" tooling/dev/toolchain.py ` | 0.052 | 0.145 |
| `task: [python-environment-check] uv lock --check --offline` | 0.197 | 0.035 |
| `task: [python-environment-check] uv sync --check --locked --offline --all-packages` | 0.232 | 0.119 |
| `task: [lint] uv run --no-sync ruff check . ` | 0.351 | 0.144 |
| `task: [fmt-check] uv run --no-sync ruff format --check . ` | 0.495 | 0.067 |
| `task: [type-all] uv run --no-sync python scripts/type.py --all --clean ` | 0.562 | 31.472 |
| `task: [test-fast] uv run --no-sync python scripts/test.py --fast ` | 32.034 | 192.686 |
| `task: [lint-imports] uv run --no-sync lint-imports ` | 224.720 | 16.505 |
| `task: [arch-smells] uv run --no-sync python scripts/architecture/check_architecture_smells.py ` | 241.225 | 10.679 |
| `task: [web-environment-check] bun tooling/dev/bun-workspace.mjs ` | 251.904 | 0.666 |
| `task: [web-lint] bun run lint ` | 252.570 | 1.828 |
| `task: [web-type] bun run type ` | 254.398 | 43.911 |
| `task: [web-product-check] bun run audit:routes ` | 298.309 | 0.063 |
| `task: [web-token-check] bun run audit:tokens:dead-links --ci ` | 298.372 | 0.136 |
| `task: [web-architecture] bun run arch:check ` | 298.508 | 3.030 |
| `task: [web-test] bun run test:unit ` | 301.538 | 85.830 |
| `task: [python-environment-check] uv lock --check --offline` | 387.368 | 0.046 |
| `task: [python-environment-check] uv sync --check --locked --offline --all-packages` | 387.414 | 0.169 |
| `task: [contract-static] uv run --no-sync python -m tooling.contracts.check_contract ` | 387.583 | 14.532 |
| `task: [contract-conformance] uv run --no-sync pytest apps/backend/tests/contract/test_openapi_conformance.py -q -n0 --no-cov ` | 402.115 | 15.477 |
| `task: [cohort-compatibility-check] uv run --no-sync python -m tooling.release.compatibility_policy ` | 417.592 | 0.095 |
| `task: [python-environment-check] uv lock --check --offline` | 417.687 | 0.031 |
| `task: [python-environment-check] uv sync --check --locked --offline --all-packages` | 417.718 | 0.051 |
| `task: [harness-validate] uv run --no-sync python tooling/agent_harness/validate.py ` | 417.769 | 1.432 |
| `task: [harness-test] uv run --no-sync python -m pytest tooling/agent_harness/tests -q -n0 --no-cov ` | 419.201 | 91.880 |
| `task: [tooling-test] uv run --no-sync pytest tooling/dev/tests tooling/contracts/tests tooling/quality/tests -q -n0 --no-cov ` | 511.081 | 34.206 |
| `task: [tooling-test] bun test tooling/quality/tests/bun_workspace.test.mjs` | 545.287 | 0.091 |
| `task: [harness-type] uv run --no-sync basedpyright tooling/agent_harness ` | 545.378 | 1.028 |

## 静态存量


每格为文件数 / AST 函数数；“unit”仅表示目录。

| owner | unit | integration | contract | e2e | other |
|---|---:|---:|---:|---:|---:|
| apps/backend | 188 / 1659 | 69 / 521 | 2 / 3 | 14 / 105 | 8 / 49 |
| packages/agent | 59 / 352 | — | — | — | — |
| packages/analysis | 51 / 809 | 2 / 14 | — | — | — |
| packages/application | 269 / 3412 | 30 / 207 | — | — | — |
| packages/backtest | 42 / 794 | 7 / 83 | — | — | 1 / 3 |
| packages/data | 192 / 2111 | 12 / 101 | — | — | — |
| packages/execution | 56 / 775 | — | — | — | — |
| packages/features | 70 / 1051 | — | — | — | — |
| packages/kernel | 18 / 285 | — | — | — | — |
| packages/platform | 53 / 435 | 7 / 149 | — | — | — |
| packages/portfolio | 29 / 268 | — | — | — | — |
| packages/risk | 33 / 190 | — | — | — | — |
| packages/strategy | 49 / 798 | 4 / 44 | — | — | — |
| scripts | — | — | — | — | 3 / 17 |
| tooling/agent_harness | — | — | — | — | 7 / 105 |
| tooling/contracts | — | — | — | — | 5 / 34 |
| tooling/dev | — | — | — | — | 6 / 35 |
| tooling/quality | — | — | — | — | 3 / 32 |
| tooling/release | — | — | — | — | 5 / 44 |

目录汇总：unit 1,109 / 12,939；integration 131 / 1,119；contract 2 / 3；e2e 14 / 105；other 38 / 319。



## 重现动态 inventory

使用仓库已准备的 Python，下面插件只读取已收集 item，在仓外唯一命名目录保存。不要使用 `queue.py` 等标准库同名脚本；本次第一次探针因此发生导入污染，已停止并作废，最终数据来自修正后的运行。

```python
import json
from pathlib import Path

def pytest_addoption(parser):
    parser.addoption('--audit-inventory')

def pytest_collection_finish(session):
    destination = session.config.getoption('audit_inventory')
    if destination:
        records = [{'nodeid': item.nodeid,
                    'markers': sorted({m.name for m in item.iter_markers()}),
                    'fixtures': sorted(item.fixturenames)} for item in session.items]
        Path(destination).write_text(json.dumps(records)+'\n')
```

```sh
# 将插件存成 <probe-dir>/inventory_probe.py；每个 owner 单独新进程执行。
PYTHONPATH=<probe-dir> PYTHON_KEYRING_BACKEND=keyring.backends.null.Keyring \
  .venv/bin/python -m pytest -o addopts= --import-mode=importlib \
  --collect-only -q -p inventory_probe --audit-inventory=<output.json> [<owner>/tests]
```

无路径时使用 pyproject 默认 testpaths。用完整 nodeid 对齐，比较 marker 集合；fast 模拟条件为 marker 与 `{slow,integration,snapshot,sandbox_live,capacity}` 无交集。不是按目录猜测标记。代码 inventory 与 runtime case 数统计口径不同。


## 动态 inventory 对照

全仓17,139 collected case；模拟 fast15,781，其中PIT440；全部PIT600。marker可重叠，不可相加作为总数。全仓各 marker：

```json
{
  "unit": 15809,
  "parametrize": 3825,
  "asyncio": 383,
  "pit": 600,
  "integration": 1357,
  "serial": 1244,
  "skipif": 28,
  "capacity": 7,
  "e2e": 84,
  "slow": 10,
  "snapshot": 3,
  "hypothesis": 24,
  "timeout": 2,
  "cli_test": 86,
  "skip": 18,
  "usefixtures": 16,
  "sandbox_live": 1
}
```

各owner nodeid 集合均与全仓对应子集相等。差异来自标记，不是文件漏收集。

| owner | collected | owner/full fast | owner collect wall(s) | marker变化用例数 | 全仓额外附加的标记计数 |
|---|---:|---:|---:|---:|---|
| packages/agent | 631 | 631 / 631 | 2.447 | 631 | {'full_only_unit': 631} |
| packages/analysis | 1301 | 1301 / 1283 | 1.269 | 1301 | {'full_only_integration': 18, 'full_only_serial': 18, 'full_only_unit': 1283} |
| packages/application | 4535 | 4469 / 4281 | 7.475 | 3963 | {'full_only_integration': 188, 'full_only_serial': 253, 'full_only_unit': 3710} |
| apps/backend | 2803 | 2136 / 2136 | 10.918 | 0 | {} |
| packages/backtest | 959 | 955 / 875 | 1.078 | 954 | {'full_only_integration': 83, 'full_only_serial': 83, 'full_only_unit': 871} |
| packages/data | 2291 | 2149 / 2149 | 2.083 | 0 | {} |
| packages/execution | 884 | 884 / 884 | 1.219 | 0 | {} |
| packages/features | 1208 | 1208 / 1208 | 1.288 | 1194 | {'full_only_unit': 1194} |
| packages/kernel | 285 | 285 / 285 | 0.992 | 285 | {'full_only_unit': 285} |
| packages/platform | 598 | 449 / 449 | 1.126 | 149 | {'full_only_serial': 149} |
| packages/portfolio | 320 | 320 / 320 | 1.555 | 320 | {'full_only_unit': 320} |
| packages/risk | 242 | 242 / 242 | 0.765 | 242 | {'full_only_unit': 242} |
| packages/strategy | 1082 | 1082 / 1038 | 1.396 | 1082 | {'full_only_integration': 44, 'full_only_serial': 44, 'full_only_unit': 1038} |

具体差异样本（全仓新增，owner入口缺失）：

- `packages/analysis/tests/integration/test_experiment_database_migration.py::test_close_all_closes_worker_connections_and_prevents_resurrection`：integration, serial
- `packages/analysis/tests/integration/test_experiment_database_migration.py::test_close_all_serializes_with_inflight_connection_acquisition`：integration, serial
- `packages/application/tests/integration/process/execution/test_delivery_integration.py::TestBuildContextFieldsCorrectness::test_action_fields_rounded`：integration, serial
- `packages/application/tests/integration/process/execution/test_delivery_integration.py::TestBuildContextFieldsCorrectness::test_context_fields`：integration, serial
- `packages/backtest/tests/integration/test_backtest_e2e_smoke.py::TestE2ENegativeScenarios::test_bearish_market`：integration, serial
- `packages/backtest/tests/integration/test_backtest_e2e_smoke.py::TestE2ENegativeScenarios::test_single_day_backtest`：integration, serial
- `packages/platform/tests/integration/observability/test_init_integration.py::TestInit::test_init_environment_alias_dev`：serial
- `packages/platform/tests/integration/observability/test_init_integration.py::TestInit::test_init_environment_alias_prod`：serial
- `packages/strategy/tests/integration/alpha/test_etf_rotation_e2e.py::TestETFRotationE2E::test_all_locked_returns_empty`：integration, serial
- `packages/strategy/tests/integration/alpha/test_etf_rotation_e2e.py::TestETFRotationE2E::test_etf_rotation_recommendation`：integration, serial

## 路径选择矩阵

直接调用当前 `classify_diff` / `verification_commands` / `required_jobs`；每场景清除进程内 owner probe cache。security analysis按ci._emit同一表达式记录。planner耗时包括实际owner预收集，但**未执行**表中计划命令。删除/重命名以不存在的旧路径及新路径模拟selector输入，没有真的改动源码；不等同完整Git raw-diff端到端验证。当前普通backend PR仍选全仓后端shards，local owner-only本身不是整体覆盖缺口的证明。

### docs

输入：`docs/engineering/testing.md`

level=`docs`；planner=0.03s；security analysis=False。

本地：

```sh
# no validation commands
```

PR jobs：`repository-policy`, `security-supply-chain`。

### skill

输入：`.agents/skills/ditto-pit-safety/SKILL.md`

level=`skills`；planner=0.03s；security analysis=False。

本地：

```sh
task harness-validate
```

PR jobs：`repository-policy`, `security-supply-chain`, `skill-validation`。

### test_only

输入：`packages/kernel/tests/unit/test_identity.py`

level=`backend-tests`；planner=0.0s；security analysis=True。

本地：

```sh
uv run --no-sync ruff format --check packages/kernel/tests/unit/test_identity.py
uv run --no-sync ruff check packages/kernel/tests/unit/test_identity.py
task type -- --tests
uv run --no-sync pytest -q --import-mode=importlib packages/kernel/tests/unit/test_identity.py
```

PR jobs：`api-contract`, `architecture-harness`, `backend-capacity`, `backend-quality`, `backend-shards`, `backend-tests`, `backend-types`, `repository-policy`, `security-supply-chain`, `system-e2e`, `web-build`。

### kernel

输入：`packages/kernel/src/ditto_kernel/identity.py`

level=`backend`；planner=0.966s；security analysis=True。

本地：

```sh
task lint
task fmt-check
task type-all
task test -- --fast packages/kernel/tests
```

PR jobs：`api-contract`, `architecture-harness`, `backend-capacity`, `backend-quality`, `backend-shards`, `backend-tests`, `backend-types`, `repository-policy`, `security-supply-chain`, `system-e2e`, `web-build`。

### platform

输入：`packages/platform/src/ditto_platform/foundation/util/dates.py`

level=`backend`；planner=1.094s；security analysis=True。

本地：

```sh
task lint
task fmt-check
task type-all
task test -- --fast packages/platform/tests
```

PR jobs：`api-contract`, `architecture-harness`, `backend-capacity`, `backend-quality`, `backend-shards`, `backend-tests`, `backend-types`, `repository-policy`, `security-supply-chain`, `system-e2e`, `web-build`。

### ordinary_agent

输入：`packages/agent/src/ditto_agent/grounding.py`

level=`backend`；planner=2.407s；security analysis=True。

本地：

```sh
task lint
task fmt-check
task type-all
task test -- --fast packages/agent/tests
```

PR jobs：`api-contract`, `architecture-harness`, `backend-capacity`, `backend-quality`, `backend-shards`, `backend-tests`, `backend-types`, `repository-policy`, `security-supply-chain`, `system-e2e`, `web-build`。

### high_risk_application

输入：`packages/application/src/ditto_application/queries/etf_candidates.py`

level=`high-risk`；planner=7.326s；security analysis=True。

本地：

```sh
task lint
task fmt-check
task type-all
task test -- --fast packages/application/tests
task pit
```

PR jobs：`api-contract`, `architecture-harness`, `backend-capacity`, `backend-quality`, `backend-shards`, `backend-tests`, `backend-types`, `container-smoke`, `platform-smoke`, `release-policy`, `repository-policy`, `security-supply-chain`, `skill-validation`, `system-e2e`, `web-build`, `web-prototype`, `web-quality`。

### cross_backend

输入：`packages/application/src/ditto_application/queries/etf_candidates.py`、`packages/agent/src/ditto_agent/grounding.py`

level=`high-risk`；planner=7.551s；security analysis=True。

本地：

```sh
task lint
task fmt-check
task type-all
task test -- --fast packages/agent/tests packages/application/tests
task pit
```

PR jobs：`api-contract`, `architecture-harness`, `backend-capacity`, `backend-quality`, `backend-shards`, `backend-tests`, `backend-types`, `container-smoke`, `platform-smoke`, `release-policy`, `repository-policy`, `security-supply-chain`, `skill-validation`, `system-e2e`, `web-build`, `web-prototype`, `web-quality`。

### web

输入：`apps/web/src/components/ui/button.tsx`

level=`web`；planner=0.0s；security analysis=True。

本地：

```sh
task check-web
```

PR jobs：`api-contract`, `repository-policy`, `security-supply-chain`, `system-e2e`, `web-build`, `web-prototype`, `web-quality`。

### cross_stack

输入：`packages/kernel/src/ditto_kernel/identity.py`、`apps/web/src/components/ui/button.tsx`

level=`cross-stack`；planner=0.0s；security analysis=True。

本地：

```sh
task check
task test-system
```

PR jobs：`api-contract`, `architecture-harness`, `backend-capacity`, `backend-quality`, `backend-shards`, `backend-tests`, `backend-types`, `container-smoke`, `platform-smoke`, `release-policy`, `repository-policy`, `security-supply-chain`, `skill-validation`, `system-e2e`, `web-build`, `web-prototype`, `web-quality`。

### contract

输入：`contracts/openapi/v1.json`

level=`contract`；planner=0.0s；security analysis=True。

本地：

```sh
task check
task test-system
```

PR jobs：`api-contract`, `architecture-harness`, `backend-capacity`, `backend-quality`, `backend-shards`, `backend-tests`, `backend-types`, `container-smoke`, `platform-smoke`, `release-policy`, `repository-policy`, `security-supply-chain`, `skill-validation`, `system-e2e`, `web-build`, `web-prototype`, `web-quality`。

### tooling

输入：`tooling/quality/slow_test_gate.py`

level=`unknown`；planner=0.0s；security analysis=True。

本地：

```sh
task check
```

PR jobs：`api-contract`, `architecture-harness`, `backend-capacity`, `backend-quality`, `backend-shards`, `backend-tests`, `backend-types`, `container-smoke`, `platform-smoke`, `release-policy`, `repository-policy`, `security-supply-chain`, `skill-validation`, `system-e2e`, `web-build`, `web-prototype`, `web-quality`。

### lock

输入：`uv.lock`

level=`root`；planner=0.0s；security analysis=True。

本地：

```sh
task check
```

PR jobs：`api-contract`, `architecture-harness`, `backend-capacity`, `backend-quality`, `backend-shards`, `backend-tests`, `backend-types`, `container-smoke`, `platform-smoke`, `release-policy`, `repository-policy`, `security-supply-chain`, `skill-validation`, `system-e2e`, `web-build`, `web-prototype`, `web-quality`。

### config

输入：`pyproject.toml`

level=`root`；planner=0.0s；security analysis=True。

本地：

```sh
task check
```

PR jobs：`api-contract`, `architecture-harness`, `backend-capacity`, `backend-quality`, `backend-shards`, `backend-tests`, `backend-types`, `container-smoke`, `platform-smoke`, `release-policy`, `repository-policy`, `security-supply-chain`, `skill-validation`, `system-e2e`, `web-build`, `web-prototype`, `web-quality`。

### deleted_test

输入：`packages/kernel/tests/unit/test_removed_example.py`

level=`backend-tests`；planner=0.0s；security analysis=True。

本地：

```sh
task type -- --tests
uv run --no-sync pytest -q --import-mode=importlib packages/kernel/tests
```

PR jobs：`api-contract`, `architecture-harness`, `backend-capacity`, `backend-quality`, `backend-shards`, `backend-tests`, `backend-types`, `repository-policy`, `security-supply-chain`, `system-e2e`, `web-build`。

### renamed_owner_paths

输入：`packages/kernel/src/ditto_kernel/removed_example.py`、`packages/platform/src/ditto_platform/foundation/util/dates.py`

level=`backend`；planner=1.235s；security analysis=True。

本地：

```sh
task lint
task fmt-check
task type-all
task test -- --fast packages/kernel/tests packages/platform/tests
```

PR jobs：`api-contract`, `architecture-harness`, `backend-capacity`, `backend-quality`, `backend-shards`, `backend-tests`, `backend-types`, `repository-policy`, `security-supply-chain`, `system-e2e`, `web-build`。

### unknown

输入：`unmapped/new-file.xyz`

level=`unknown`；planner=0.0s；security analysis=True。

本地：

```sh
task check
```

PR jobs：`api-contract`, `architecture-harness`, `backend-capacity`, `backend-quality`, `backend-shards`, `backend-tests`, `backend-types`, `container-smoke`, `platform-smoke`, `release-policy`, `repository-policy`, `security-supply-chain`, `skill-validation`, `system-e2e`, `web-build`, `web-prototype`, `web-quality`。

## 动态探针限制

本次清空 pytest addopts 以单进程观察 collection，不测 xdist 每worker的收集成本。集合/marker观察有效；它与含xdist和详细日志的真实执行 wall不能直接相减分解开销。测试phase另用只观察report的插件记录，setup/call/teardown为case累计秒数；并行重叠不当作用户等待。


## 正式本地测量记录

启动时间为Unix epoch秒（UTC）。这些记录均exit0；不是对未测入口的通过声明。

| label | started epoch | wall(s) | command |
|---|---:|---:|---|
| check | 1790553318.448 | 546.406 | `task check` |
| type-tests-verified | 1790554439.393 | 9.737 | `task type -- --tests` |
| pit-verified | 1790554449.167 | 91.561 | `task pit` |
| system | 1790553973.252 | 255.907 | `task test-system` |
| collect-all | 1790554540.766 | 17.666 | `.venv/bin/python -m pytest -o addopts= --import-mode=importlib --collect-only -q -p inventory_probe --audit-inventory /tmp/ditto335/inventory-all.json` |
| kernel-fast-1 | 1790554613.299 | 3.732 | `task test -- --fast packages/kernel/tests --junitxml=/tmp/ditto335/kernel-1.xml` |
| kernel-fast-2 | 1790554617.067 | 3.695 | `task test -- --fast packages/kernel/tests --junitxml=/tmp/ditto335/kernel-2.xml` |
| web-coverage | 1790554620.800 | 74.356 | `task web-coverage` |
| application-fast | 1790554741.757 | 118.999 | `task test -- --fast packages/application/tests -p phase_probe --junitxml=/tmp/ditto335/application.xml` |
| ruff-isolated-1 | 1790554860.796 | 0.447 | `uv run --no-sync ruff check . --cache-dir=/tmp/ditto335/ruff-cache` |
| ruff-isolated-2 | 1790554861.278 | 0.066 | `uv run --no-sync ruff check . --cache-dir=/tmp/ditto335/ruff-cache` |
| precommit-source-1 | 1790554861.381 | 0.749 | `/Users/chevy/Desktop/code/ditto/.venv/bin/pre-commit run --files packages/kernel/src/ditto_kernel/identity.py --hook-stage pre-commit` |
| precommit-source-2 | 1790554862.165 | 0.657 | `/Users/chevy/Desktop/code/ditto/.venv/bin/pre-commit run --files packages/kernel/src/ditto_kernel/identity.py --hook-stage pre-commit` |

uv0.12.13在仓库允许的>=0.12.7,<0.13范围；未改lockfile。precommit-source在独立报告worktree使用主工作区已准备venv，其他本地性能命令在固定源码主工作区运行。runner对自身子进程设null keyring/禁自动下载Python，并逐命令捕获stdout/stderr与exit；首次污染尝试不在此表。

## Application phase观察

```python
import json
from pathlib import Path

_phases = []

def pytest_runtest_logreport(report):
    _phases.append({'nodeid': report.nodeid, 'phase': report.when, 'outcome': report.outcome, 'duration_s': report.duration})

def pytest_sessionfinish(session, exitstatus):
    if not hasattr(session.config, 'workerinput'):
        Path('/tmp/ditto335/application-phases.json').write_text(json.dumps(_phases) + '\n')
```

命令见上表；通过PYTHONPATH加载仓外唯一名称插件。仅controller保存xdist汇总report，避免worker重复计数。

| phase | 全部累计秒数 | 多选188例累计秒数 |
|---|---:|---:|
| setup | 3.215 | 0.191 |
| call | 234.543 | 49.114 |
| teardown | 1.033 | 0.052 |

| 文件 | setup+call+teardown累计(s) |
|---|---:|
| `packages/application/tests/unit/process/experiments/test_planning_process_unit.py` | 101.422 |
| `packages/application/tests/integration/test_r3_evidence_closure_golden.py` | 25.257 |
| `packages/application/tests/unit/process/experiments/test_selection_evidence_artifact_unit.py` | 15.277 |
| `packages/application/tests/unit/process/experiments/test_evidence_collector_unit.py` | 14.528 |
| `packages/application/tests/integration/test_experiment_planning_integration.py` | 13.587 |
| `packages/application/tests/unit/process/experiments/test_planning_request_builder_unit.py` | 10.419 |
| `packages/application/tests/unit/process/experiments/test_walk_forward_evidence_collection_unit.py` | 9.161 |
| `packages/application/tests/unit/process/experiments/test_research_backtest_factory_unit.py` | 8.754 |

| 最慢phase样本 | phase | seconds |
|---|---|---:|
| `packages/application/tests/integration/test_r3_evidence_closure_golden.py::test_r3_evidence_closure_drives_review_packet_and_completed_status[cost-match-etf]` | call | 6.763 |
| `packages/application/tests/integration/test_experiment_planning_integration.py::test_durable_execution_resolver_uses_only_exact_strategy_and_snapshot_identity` | call | 6.761 |
| `packages/application/tests/integration/test_r3_evidence_closure_golden.py::test_r3_evidence_closure_drives_review_packet_and_completed_status[cost-match-stock]` | call | 5.451 |
| `packages/application/tests/integration/test_r3_evidence_closure_golden.py::test_r3_evidence_closure_drives_review_packet_and_completed_status[cost-drift-stock]` | call | 5.144 |
| `packages/application/tests/integration/test_r3_live_gate_binding_integration.py::test_verified_live_gate_survives_real_collector_persistence_and_reopen` | call | 4.896 |
| `packages/application/tests/integration/test_r3_evidence_closure_golden.py::test_r3_evidence_closure_drives_review_packet_and_completed_status[cost-drift-etf]` | call | 4.725 |
| `packages/application/tests/integration/test_experiment_planning_integration.py::test_launch_is_durable_and_exact_hash_replay_is_zero_write` | call | 4.442 |
| `packages/application/tests/unit/process/experiments/test_planning_process_unit.py::test_authority_evidence_hash_and_complete_semantics_are_in_plan_identity` | call | 3.644 |
| `packages/application/tests/unit/process/experiments/test_planning_process_unit.py::test_partial_draft_rejects_immutable_request_drift_without_writes` | call | 3.545 |
| `packages/application/tests/unit/process/experiments/test_planning_process_unit.py::test_partial_draft_replays_exactly_and_queued_replay_is_zero_write` | call | 3.351 |

这些数据没有CPU/memory profiler和严格资源争用对照；不将函数体内装配当作pytest fixture setup，也不将worker累计时间相加当wall。
