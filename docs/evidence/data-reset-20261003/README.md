# 开发运行时数据全量重置记录(#396)

- 执行日期: 2026-10-03
- 代码 SHA: c25358cf9414a58c9e6689bcfe09385f50b6e7ad
- 授权: #390 维护者确认(项目未上线,全部开发数据/历史 payload/缓存/物化/运行记录可清空重建,无备份/迁移/回滚要求)

## 清理目标(精确绝对路径)

根: /Users/chevy/Desktop/code/ditto/data/
456M	data/
backups
capital
db
factors
features
freezes
fundamental
fuyao
locks
logs
macro
market
metadata
metadata.sqlite
personal-workstation-accelerated-acceptance
personal-workstation-acceptance
provider_payloads
quarantine
research
temp
trading

## 次要根(默认 XDG)
根: /Users/chevy/.local/state/ditto/
 22M	/Users/chevy/.local/state/ditto/
code-sync
derived
issue-111-local-cleanup
market
metadata
research
trading

## 执行
- 停止进程: ditto_apps.server×2+mp 子进程已 kill(见上)
- 删除: 两根全部内容

## 执行结果

- 两根已清空;以最终结构初始化(31 目录,无 db/freezes/fundamental-forecast/根下孤儿库,治理表零创建)
- 真实摄取(2026-09-30,共 9 数据集全部 SUCCESS):calendar(396)/stock_basic(5922)/stock_daily(5572)/stock_status(5573)/adj_factor(5572)/etf_basic(1843)/etf_daily(1712)/index_basic(8000)/index_daily(173)
- 完成事实:9 COMPLETE checkpoint、9 provider snapshots、9 观察事件;幂等重跑(stock_daily 同日)SUCCESS log 仍 1 条
- 修复两个真实接缝(本 PR):basic 类无日期数据集的 intent 观察日锚;saga 校验锚点修正(enrich 派生使 log checksum 与 payload checksum 语义不同,内容身份由 chunk payload/complete_evidence_id 绑定链承载)

## 用户旅程验收状态(如实)

- universe.cn.all 创建+5922 成员(全部注册股票)成功
- 选股组装推进至历史证券池解析,被 **HISTORY_FIELDS_MISSING 阻断**:historical universe 的 status 链要求 PIT 区间形状(instrument_id/effective_from/effective_to/publication_at),而 stock_status 真实载荷为原始日频形状(source_ticker/trade_date/is_st/is_suspended);旧世界该链由手工构造的 golden 快照满足,从未与真实摄取联通过
- 该缺口为 #391 历史池设计与 #196 真实数据形状的既有裂缝,#396 如实报告不假装通过;修复需单独决策(status 链读取投影层 / stock_status 数据集形状变更),已开票跟踪
- 另发现 universe replace_constituents 存量 bug(同 effective_from 重放撞 UNIQUE),已开票跟踪
