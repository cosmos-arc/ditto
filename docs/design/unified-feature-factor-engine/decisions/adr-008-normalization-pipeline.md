# ADR-008: 标准化管线设计

**状态**: 已决策（2026-03-04）

---

## 决策：可配置管线，默认 WorldQuant 风格（Rank → ZScore）

### 默认管线（WorldQuant 风格）

```python
DEFAULT_FACTOR_PIPELINE = [
    NormalizationStage(method="cs_rank"),
    NormalizationStage(method="cs_zscore"),
]
```

**理由**：
1. 业界主流：70%+ 量化平台采用
2. 鲁棒高效：Rank 消除极端值影响
3. 实证有效：WorldQuant Alpha101 验证

---

## 预设管线

| 预设名称 | 管线 | 适用场景 |
|----------|------|---------|
| `default` | Rank → ZScore | Alpha 因子（默认） |
| `fundamental` | Winsorize → Rank → ZScore | 基本面因子（有极端异常值） |
| `institutional` | Rank → ZScore → Neutralize | 机构级因子（需行业中性化） |
| `none` | 无标准化 | 技术指标（保留原始值） |

---

## 配置模型

```python
@dataclass
class NormalizationStage:
    """标准化阶段"""
    method: Literal["winsorize", "cs_rank", "cs_zscore", "cs_demean", "neutralize"]
    params: dict[str, object] = Field(default_factory=dict)


@dataclass
class NormalizationConfig:
    """标准化配置"""
    pipeline_preset: Literal["default", "fundamental", "institutional", "none"] = "default"
    custom_stages: list[NormalizationStage] | None = None
    winsorize_sigma: float = 3.0
    neutralize_groups: list[str] = Field(default_factory=lambda: ["industry"])

    def get_pipeline(self) -> list[NormalizationStage]:
        """获取标准化管线"""
        if self.custom_stages is not None:
            return self.custom_stages

        presets = {
            "default": [
                NormalizationStage(method="cs_rank"),
                NormalizationStage(method="cs_zscore"),
            ],
            "fundamental": [
                NormalizationStage(method="winsorize", params={"sigma": self.winsorize_sigma}),
                NormalizationStage(method="cs_rank"),
                NormalizationStage(method="cs_zscore"),
            ],
            "institutional": [
                NormalizationStage(method="cs_rank"),
                NormalizationStage(method="cs_zscore"),
                NormalizationStage(method="neutralize", params={"groups": self.neutralize_groups}),
            ],
            "none": [],
        }
        return presets[self.pipeline_preset]
```

---

## 因子输出 Schema

```python
factor_output_schema = {
    "instrument_id": str,       # 标的 ID
    "trade_date": date,         # 交易日期
    "factor_id": str,           # 因子 ID
    "raw_value": float,         # 原始值（标准化前）
    "exposure": float,          # 标准化后的因子暴露
    "effective_from": date,     # PIT 生效日期
    "effective_to": date | None,# PIT 失效日期（null = 当前有效）
    "spec_hash": str,           # Spec 哈希
    "run_id": str,              # 运行 ID
}
```

---

## 业界对标

| 平台 | 默认管线 | Ditto 选择 |
|------|---------|-----------|
| WorldQuant Brain | Rank → ZScore | ✓ 采用 |
| Barra | Winsorize → ZScore → Neutralize | 可选 |
| Qlib | ZScore | Rank 更鲁棒 |
| BigQuant | Rank → ZScore | ✓ 采用 |
| **Ditto** | **Rank → ZScore** | **业界主流** |
