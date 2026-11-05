# HKEX Stock Connect 官方交易日历（北向披露锚，#693）

HKEX 官方 Stock Connect Trading Calendar CSV 原件（`Northbound Trading`
列为北向交易日），作为 hk_hold 季度段官方发布日表
（`hk_hold_disclosure.HK_HOLD_PUBLICATION_DATES`）的证据 fixture。

- 抓取日：2026-11-05
- 来源页：<https://www.hkex.com.hk/Mutual-Market/Stock-Connect/Reference-Materials/Trading-Hour,-Trading-and-Settlement-Calendar?sc_lang=en>
- 2025：`2025-calendar_csv_e.csv`
- 2026：`2026-calendar_csv_e.csv`
- 规则依据：HKEX 2024-04-12 公告（北向持股季度化，季末后第 5 个北向交易日发布）
  <https://www.hkex.com.hk/News/Market-Communications/2024/2404122news?sc_lang=en>
- 2024 无该 CSV：2024-09-30 季的发布日由 SSE trade_cal 扣 2024Q4 HKEX
  休市推导（窗口内额外休市仅 10-11 重阳），见模块注释。

HKEX 每年发布次年日历后：下载新 CSV 入本目录，并在
`HK_HOLD_PUBLICATION_DATES` 追加新季度行（测试会从本 fixture 复算校验）。
