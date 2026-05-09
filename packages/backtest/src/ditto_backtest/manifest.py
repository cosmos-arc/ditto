"""
回测运行清单 — 类型定义与构建函数 Facade.

- RunMode(StrEnum): 4 种运行模式
- RuleRef(frozen): 单条规则引用（instrument + 版本 + 时间锚点）
- RunManifest(frozen): 一次引擎运行的完整清单
- RuleRefCollector: 运行期间收集规则引用（first_observed 策略）
- build_run_manifest: 从引擎运行结果构建 RunManifest
- serialize_manifest: canonical JSON 序列化（字节级稳定）

类型定义在 manifest_types.py，构建函数在 manifest_build.py。
"""

from ditto_backtest.manifest_build import (
    RuleRefCollector,
    build_run_manifest,
    hash_config,
    hash_spec,
    serialize_manifest,
)
from ditto_backtest.manifest_types import (
    InputRef,
    RuleRef,
    RunManifest,
    RunMode,
)

__all__ = [
    "InputRef",
    "RuleRef",
    "RuleRefCollector",
    "RunManifest",
    "RunMode",
    "build_run_manifest",
    "hash_config",
    "hash_spec",
    "serialize_manifest",
]
