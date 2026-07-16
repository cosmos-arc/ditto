# 产出物结构模板

> 定义 `/ditto-product-arch` 的产出物结构和格式规范。
> 主 skill 文件引用此文件获取具体模板。

---

## 产品准则文档 (00_ditto_product_criteria.md)

> design-cycle 和 page-contract 的审查标准。由 product-arch Phase 2 DESIGN 提取，Phase 4 落盘。

```
1. 密度准则
   ├─ L1 全局密度（导航/标题/间距的一致性标准）
   ├─ L2 区域密度（不同区域的信息密度分级）
   └─ L3 组件密度（列表/卡片/表格的行高与间距规范）

2. 字号映射
   ├─ 页面标题 → font-size token
   ├─ 区域标题 → font-size token
   ├─ 正文 → font-size token
   ├─ 标签/辅助文字 → font-size token
   └─ 数据展示 → font-size token

3. 间距梯度
   ├─ 组件内间距（padding）
   ├─ 组件间间距（gap）
   ├─ 区域间间距（section gap）
   └─ 页面边距（page padding）

4. 色彩使用原则
   ├─ 品牌色使用范围
   ├─ 语义色映射（成功/警告/错误/信息）
   ├─ 中性色梯度
   └─ 数据可视化色彩规范

5. 品牌气质锚定
   ├─ 视觉风格关键词（如 Graphite Studio）
   ├─ 克制度定义
   ├─ 高级感标准
   └─ 参考竞品视觉特征
```

---

## 信息架构文档 (01_product_information_architecture.md)

```
1. 产品定位与价值主张
   ├─ 一句话定位
   ├─ 核心价值主张（3 个差异化点）
   └─ 目标用户画像摘要

2. 用户画像与核心需求
   ├─ Persona A（专业量化交易员）
   │   ├─ 行为模式
   │   ├─ 核心痛点
   │   └─ 期望
   ├─ Persona B（技术型投资者转量化）
   │   └─ ...
   └─ 内部团队角色映射

3. 核心工作流
   Observe → Discover → Research → Validate → Execute → Monitor/Improve
   ├─ 每个阶段的输入/输出
   └─ 阶段间的触发条件

4. 信息架构
   ├─ 4.1 导航模型（sidebar + tabs + command palette）
   ├─ 4.2 顶层结构（Home / Markets / Research / Trading / AI / Platform）
   ├─ 4.3 页面层级关系（≤ 3 层）
   ├─ 4.4 导航路径矩阵（从 A 可到 B/C/D）
   └─ 4.5 内容分组逻辑（按用户心智模型，非技术架构）

5. 标签体系与术语表
   ├─ 5.1 中文标签体系
   ├─ 5.2 英文标签对照
   └─ 5.3 资产类别术语

6. 用户流程
   ├─ 6.1 核心任务流程（happy path + 错误分支）
   ├─ 6.2 跨页面流程
   └─ 6.3 渐进展示策略（首屏核心 → 滚动次要 → 点击详情）

7. 页面优先级
   ├─ Batch 1: MVP 核心
   ├─ Batch 2: 增强体验
   └─ Batch 3: 差异化功能
```

---

## 页面蓝图文档 (02_core_page_blueprints.md)

每个页面必须包含以下 section（缺失任一项 = 文档不完整）：

```
页面: [名称]
├─ 目标与角色
│   ├─ 页面目标（一句话）
│   └─ 主要用户角色
├─ 主/辅工作面
│   ├─ 主工作面（Primary Work Surface）
│   └─ 辅工作面（Secondary Work Surfaces）
├─ 默认信息排序（首屏优先级）
├─ 核心模块清单
├─ Tab Content Sections
│   ├─ Tab: [名称]
│   │   ├─ 子模块清单
│   │   ├─ 数据字段（来源: 01 IA 或 04 状态规范）
│   │   └─ 交互说明
│   └─ ...
├─ Overlay Registry
│   ├─ Overlay: [名称] (Modal/Drawer/Sheet/Toast)
│   │   ├─ 触发条件
│   │   ├─ 内容结构
│   │   └─ 关闭行为
│   │   ⚠️ 破坏性操作必须有 Confirm Dialog
│   └─ ...
├─ Component × State Matrix
│   ├─ 行 = 组件名
│   ├─ 列 = 状态（default/loading/empty/failed/stale/selected/bulk/running/blocker...）
│   └─ 单元格 = 该组件在该状态下的表现描述
│       ⚠️ 数据组件必须定义 loading/empty/failed 三态
├─ Page Contract Mapping
│   ├─ route: 页面路由路径（如 /, /markets, /markets/a-shares）
│   ├─ shellFamily: Shell 族（见 enums.md 7 枚举值）
│   ├─ pagePattern: 页面模式（见 enums.md 8 枚举值）
│   └─ 模块→Slot 映射表
│       ├─ shell 级区块 → SHELL_SLOT_MAP slot 名
│       ├─ 页面级区块 → subSlot 名（kebab-case）
│       └─ 每个核心模块必须出现
├─ 主 CTA
├─ Design Token Requirements
│   ├─ 需新增的 Token
│   │   ├─ Token 名称 | 类型 | 用途 | 来源页面/模块
│   │   └─ ...
│   ├─ 需废弃的 Token
│   │   ├─ Token 名称 | 替代 | 原因
│   │   └─ ...
│   └─ 需修改的 Token
│       ├─ Token 名称 | 旧值 | 新值 | 原因
│       └─ ...
├─ 与其他页面的关系
└─ 线框图（ASCII art）
```

---

## 状态规范文档 (04_interaction_state_spec.md)

> 通用状态定义 + 页面级状态映射。由 product-arch Phase 2 UX Strategist 提取，Phase 4 落盘。
> design-cycle Phase 0.5 CREATE 和 page-contract --create 的直接输入。

```
1. 通用状态定义
   ├─ loading: 加载态（Skeleton / Spinner / 骨架屏）
   │   ├─ 触发条件: 首次加载、刷新、搜索中
   │   ├─ 展示规范: Skeleton 占位尺寸与数据组件一致
   │   └─ 超时处理: > 3s 显示提示，> 10s 提供取消/重试
   ├─ empty: 空态（Empty State / Zero State）
   │   ├─ 触发条件: 数据为空、筛选无结果、未开始使用
   │   ├─ 展示规范: 插画 + 说明文字 + CTA 按钮
   │   └─ 区分: "无数据" vs "加载中" vs "出错了"
   ├─ error: 错误态（Error State）
   │   ├─ 触发条件: 网络错误、API 失败、权限不足
   │   ├─ 展示规范: Error boundary + 错误描述 + 重试按钮
   │   └─ 级别: P0（阻断）/ P1（降级）/ P2（静默）
   ├─ stale: 过期态
   │   ├─ 触发条件: 数据超过 N 分钟未更新
   │   ├─ 展示规范: 时间戳变灰 + 刷新提示
   │   └─ 自动恢复: 轮询/WebSocket 重连后自动刷新
   └─ success: 成功态
       ├─ 触发条件: 操作完成
       ├─ 展示规范: Toast / 内联确认
       └─ 持续时间: 3s 自动消失

2. 页面状态映射
   每个页面 MUST 列出其组件的状态覆盖矩阵：
   ├─ 页面: [名称]
   │   ├─ 组件 A: default / loading / empty / error / stale / selected / running
   │   ├─ 组件 B: default / loading / empty / error
   │   └─ ...

3. 状态转换规则
   ├─ 触发条件 → 新状态（自动）
   ├─ 用户操作 → 新状态（手动）
   └─ 错误恢复路径

4. UI 组件规范
   ├─ Skeleton: 占位尺寸比例、动画、shimmer 效果
   ├─ Toast: 位置（top-right）、持续时间、层级
   ├─ Error Boundary: 降级策略、重试按钮位置
   └─ Spinner: 使用场景（全屏 vs 内联 vs 按钮）
```

---

## 审计报告模板

```markdown
# Ditto 产品架构审计报告

## 审计范围
- IA 文档: [版本/状态]
- 蓝图文档: [版本/状态]
- 审计日期: YYYY-MM-DD

## 完整性评分

| 维度 | 评分 | 说明 |
|------|------|------|
| IA 覆盖度 | X/10 | 已知 N 个页面，蓝图覆盖 M 个 |
| 标签一致性 | X/10 | 发现 K 处标签不一致 |
| 导航可达性 | X/10 | 发现 J 个不可达页面/状态 |
| 流程完整性 | X/10 | 核心任务覆盖 L/M |
| 文档同步度 | X/10 | 与设计决策有 D 处不同步 |
| 状态定义覆盖 | X/10 | Tab 面板 M/N, Overlay K 个, 状态矩阵 L/N 组件 |
| Constitution 合规 | X/10 | P0 违规 N 条, P1 违规 N 条 |

## 发现的问题

### P0: 结构性问题
- [问题描述] — [影响] — [建议修复]

### P1: 一致性问题
- [问题描述] — [影响] — [建议修复]

### P2: 优化建议
- [建议内容] — [预期收益]

## Constitution 合规检查

| 约束 ID | 约束描述 | 合规状态 | 违规详情 |
|---------|---------|---------|---------|
| T1 | ... | ✅ / ❌ | ... |

## 待同步清单
- [ ] [同步项 1]: [源文档] → [目标文档]
```
