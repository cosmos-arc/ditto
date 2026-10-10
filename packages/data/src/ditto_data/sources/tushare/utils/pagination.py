"""
Tushare 端点分页契约（#431）.

服务端单次提取上限按端点各异（官方专页：daily=6000、fund_daily=5000、
index_global=4000、fund_adj=2000；未消费端点示例：vix_index=300、
fut_basic=10000），不存在统一页宽。只有请求页宽不超过服务端上限时，
"返回行数 < 请求页宽"才能证明取尽；请求页宽超过服务端上限会静默截断
（离线复现：2501 行源、服务端 cap 2000、请求 limit 9000 仅取回 2000）。

本表只声明当前仓库实际消费的端点，官方上限以各端点专页为准
（2026-10-04 核查，来源见 docs/research/2026-10-04-tushare-second-review.md）：

- 已核实上限的端点用精确值；
- 未核实上限的端点用保守默认 2000（已知官方列表端点上限的最小值；
  唯一低于 2000 的 vix_index=300 未被本仓库消费）。官方确认具体上限后
  应改为精确值，不得以默认值冒充接口合同。

所有已消费端点均支持 pro HTTP 通用 ``limit/offset`` 参数；若未来接入不支持
offset 的端点，须在本模块注明并让调用方按官方窗口参数分片，不得走自动
翻页。client 的重复行守卫会在运行时拦截服务端忽略 offset 的情况。
"""

from __future__ import annotations

__all__ = ["resolve_page_size"]

# 已核实官方单次提取上限的端点 → 上限（tushare.pro/document/2 各专页）。
_DOCUMENTED_PAGE_SIZES: dict[str, int] = {
    "etf_basic": 5000,  # doc_id=385
    "etf_limit": 3000,  # doc_id=491
    "daily": 6000,  # doc_id=27，停牌不出行
    "fund_daily": 5000,  # doc_id=127，5000 积分起
    "fund_adj": 2000,  # doc_id=199，专页明确 offset/limit
    "index_global": 4000,  # doc_id=211，6000 积分
    "fut_daily": 2000,  # doc_id=138，2026-10-05 实测全日约 1075 行
    "fut_basic": 10000,  # doc_id=135，实测全表 11287 行、offset 翻页可用
    "forecast": 3500,  # doc_id=45，全市场按 ann_date 走 forecast_vip
    "sf_month": 2000,  # doc_id=310，月度窗口参数 start_m/end_m
    "index_dailybasic": 3000,  # doc_id=128，实测日覆盖 15 个大盘指数
    "pledge_stat": 1000,  # doc_id=110，单次最大 1000 行；默认 2000 会短页截断
    "stock_st": 1000,  # doc_id=397，单次最大 1000 行；默认 2000 会短页截断（#507 G3）
    # 2026-10-10 实测（t.xiaodefa.top transport）：披露日单日峰值 2353 行；
    # limit=10000 批量传输时代理中途掐断大响应（RemoteProtocolError
    # incomplete chunked read，#196 回补 51 chunk 全失败），回退 5000
    # 多数天单页覆盖且传输稳定。
    "fina_indicator_vip": 5000,
    # 2026-10-10 实测（t.xiaodefa.top transport）：以下全市场日频端点单日
    # 5000-5400 行，limit=10000 单响应正常返回；默认 2000 会拆 3 页/日
    # （#196 回补实测 adj_factor/stock_limit/moneyflow/cyq_perf/valuation
    # 吞吐损失 2-3 倍，日常增量同样每天多打 2 次请求）。
    "adj_factor": 10000,
    "stk_limit": 10000,
    "moneyflow": 10000,
    "cyq_perf": 10000,
    "daily_basic": 10000,
    "bak_basic": 10000,
    # 2026-10-10 实测（t.xiaodefa.top transport）：真实停牌名单约 1000 只/
    # 日，代理 fill-to-limit 填充到页宽且小页宽会截断唯一集（limit=2000
    # 仅 870 唯一）；limit=10000 单响应 5000 行含 1008 唯一稳定收敛，
    # 配合 fetch 层按 ts_code 去重取干净名单（#196）。
    "suspend_d": 10000,
}

_DEFAULT_PAGE_SIZE = 2000


def resolve_page_size(api_name: str) -> int:
    """按端点契约返回自动翻页使用的请求页宽。"""
    return _DOCUMENTED_PAGE_SIZES.get(api_name, _DEFAULT_PAGE_SIZE)
