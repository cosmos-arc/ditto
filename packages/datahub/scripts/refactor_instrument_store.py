#!/usr/bin/env python3
"""辅助脚本：重构 InstrumentStore 中的方法名和变量名."""

import re
from pathlib import Path

from ditto_foundation import logger


def refactor_instrument_store(content: str) -> str:
    """
    重构 InstrumentStore 文件内容.

    命名映射规则：
    - Python API: resolve_instrument_id -> resolve_instrument_id
    - Python API: source_ticker -> source_ticker
    - 数据库 SQL: 保持 instrument_id, source_ticker, security, security_mapping（不变）
    """
    # 1. 方法名替换：resolve_instrument_id -> resolve_instrument_id
    # 但保留 SQL 查询中的 instrument_id 列名
    content = re.sub(
        r"def resolve_instrument_id\(",
        "def resolve_instrument_id(",
        content,
    )

    # 2. 方法名替换：resolve_instrument_ids_batch -> resolve_instrument_ids_batch
    content = re.sub(
        r"def resolve_instrument_ids_batch\(",
        "def resolve_instrument_ids_batch(",
        content,
    )

    # 3. 参数名替换：source_ticker -> source_ticker（仅函数签名和文档字符串）
    # 注意：SQL 查询中的 source_ticker 必须保持不变

    # 4. 更新文档字符串中的描述
    content = re.sub(
        r"Resolve source_ticker to instrument_id",
        "Resolve source_ticker to instrument_id",
        content,
    )

    content = re.sub(
        r"Resolve source code to instrument_id",
        "Resolve source ticker to instrument_id",
        content,
    )

    content = re.sub(
        r"Batch resolve source_tickers to instrument_ids",
        "Batch resolve source_tickers to instrument_ids",
        content,
    )

    # 5. 更新变量名和日志消息（仅 Python 代码，不涉及 SQL）
    # 这个需要更精细的处理，因为 source_ticker 在 SQL 中必须保留

    # 6. 更新 SecurityRegistration -> InstrumentRegistration
    content = re.sub(
        r"SecurityRegistration",
        "InstrumentRegistration",
        content,
    )

    # 7. 更新注册方法的参数
    content = re.sub(
        r"registration\.source_ticker",
        "registration.source_ticker",
        content,
    )

    return content


if __name__ == "__main__":
    # 读取文件
    file_path = Path(
        "src/ditto_datahub/domains/metadata/instrument/instrument_store.py"
    )
    content = file_path.read_text(encoding="utf-8")

    # 执行重构
    new_content = refactor_instrument_store(content)

    # 写回文件
    file_path.write_text(new_content, encoding="utf-8")

    logger.info("✓ InstrumentStore 重构完成")
