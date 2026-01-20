"""
JSON Formatter 单元测试.

测试 _json_formatter 函数的核心行为，包括基本字段、额外字段和异常处理.
"""

import json
import sys
from datetime import datetime

from ditto_foundation.observability.logging import _json_formatter


class TestJSONFormatterBasicFields:
    """测试 JSON formatter 基本字段."""

    def test_basic_fields(self) -> None:
        """测试基本日志字段."""
        # [REVIEW] loguru 记录
        record = {
            "record": {
                "time": datetime(2025, 1, 11, 12, 30, 45),
                "level": type("Level", (), {"name": "INFO"})(),
                "name": "test.logger",
                "function": "test_func",
                "line": 42,
                "message": "Test message",
                "exception": None,
            },
            "extra": {},
        }

        result = _json_formatter(record)
        log_entry = json.loads(result)

        assert log_entry["timestamp"] == "2025-01-11T12:30:45"
        assert log_entry["level"] == "INFO"
        assert log_entry["logger"] == "test.logger"
        assert log_entry["function"] == "test_func"
        assert log_entry["line"] == 42
        assert log_entry["message"] == "Test message"

    def test_timestamp_format(self) -> None:
        """测试时间戳格式化为 ISO 格式."""
        now = datetime(2025, 6, 15, 14, 30, 45)
        record = {
            "record": {
                "time": now,
                "level": type("Level", (), {"name": "DEBUG"})(),
                "name": "app",
                "function": "main",
                "line": 10,
                "message": "Debug message",
                "exception": None,
            },
            "extra": {},
        }

        result = _json_formatter(record)
        log_entry = json.loads(result)

        # Verify ISO 格式
        assert log_entry["timestamp"] == "2025-06-15T14:30:45"

    def test_output_ends_with_newline(self) -> None:
        """测试输出以换行符结尾."""
        record = {
            "record": {
                "time": datetime(2025, 1, 11, 12, 0, 0),
                "level": type("Level", (), {"name": "INFO"})(),
                "name": "test",
                "function": "test",
                "line": 1,
                "message": "msg",
                "exception": None,
            },
            "extra": {},
        }

        result = _json_formatter(record)
        assert result.endswith("\n")


class TestJSONFormatterExtraFields:
    """测试 JSON formatter 额外字段."""

    def test_event_field(self) -> None:
        """测试 event 字段被正确添加."""
        record = {
            "record": {
                "time": datetime(2025, 1, 11, 12, 0, 0),
                "level": type("Level", (), {"name": "INFO"})(),
                "name": "test",
                "function": "test",
                "line": 1,
                "message": "msg",
                "exception": None,
            },
            "extra": {"event": "test_event"},
        }

        result = _json_formatter(record)
        log_entry = json.loads(result)

        assert log_entry["event"] == "test_event"

    def test_trace_id_field(self) -> None:
        """测试 trace_id 字段被正确添加."""
        record = {
            "record": {
                "time": datetime(2025, 1, 11, 12, 0, 0),
                "level": type("Level", (), {"name": "INFO"})(),
                "name": "test",
                "function": "test",
                "line": 1,
                "message": "msg",
                "exception": None,
            },
            "extra": {"trace_id": "abc123"},
        }

        result = _json_formatter(record)
        log_entry = json.loads(result)

        assert log_entry["trace_id"] == "abc123"

    def test_other_extra_fields(self) -> None:
        """测试其他额外字段被正确添加."""
        record = {
            "record": {
                "time": datetime(2025, 1, 11, 12, 0, 0),
                "level": type("Level", (), {"name": "INFO"})(),
                "name": "test",
                "function": "test",
                "line": 1,
                "message": "msg",
                "exception": None,
            },
            "extra": {"custom_field": "custom_value", "number": 42},
        }

        result = _json_formatter(record)
        log_entry = json.loads(result)

        assert log_entry["custom_field"] == "custom_value"
        assert log_entry["number"] == 42

    def test_combined_extra_fields(self) -> None:
        """测试 event、trace_id 和其他字段同时存在."""
        record = {
            "record": {
                "time": datetime(2025, 1, 11, 12, 0, 0),
                "level": type("Level", (), {"name": "INFO"})(),
                "name": "test",
                "function": "test",
                "line": 1,
                "message": "msg",
                "exception": None,
            },
            "extra": {
                "event": "data_read",
                "trace_id": "trace123",
                "source": "tushare",
                "rows": 100,
            },
        }

        result = _json_formatter(record)
        log_entry = json.loads(result)

        assert log_entry["event"] == "data_read"
        assert log_entry["trace_id"] == "trace123"
        assert log_entry["source"] == "tushare"
        assert log_entry["rows"] == 100

    def test_empty_extra(self) -> None:
        """测试空的 extra 字典."""
        record = {
            "record": {
                "time": datetime(2025, 1, 11, 12, 0, 0),
                "level": type("Level", (), {"name": "INFO"})(),
                "name": "test",
                "function": "test",
                "line": 1,
                "message": "msg",
                "exception": None,
            },
            "extra": {},
        }

        result = _json_formatter(record)
        log_entry = json.loads(result)

        # [REVIEW]
        assert "event" not in log_entry
        assert "trace_id" not in log_entry


class TestJSONFormatterException:
    """测试 JSON formatter 异常处理."""

    def test_exception_fields(self) -> None:
        """测试异常信息被正确序列化."""
        try:
            raise ValueError("Test error")
        except ValueError:
            exc_info = sys.exc_info()
            exc_type, exc_value, exc_traceback = exc_info

            record = {
                "record": {
                    "time": datetime(2025, 1, 11, 12, 0, 0),
                    "level": type("Level", (), {"name": "ERROR"})(),
                    "name": "test",
                    "function": "test",
                    "line": 1,
                    "message": "Error occurred",
                    "exception": type(
                        "Exception",
                        (),
                        {
                            "type": exc_type,
                            "value": exc_value,
                            "traceback": exc_traceback,
                        },
                    )(),
                },
                "extra": {},
            }

        result = _json_formatter(record)
        log_entry = json.loads(result)

        assert "exception" in log_entry
        assert log_entry["exception"]["type"] == "ValueError"
        assert log_entry["exception"]["value"] == "Test error"
        assert "traceback" in log_entry["exception"]

    def test_no_exception(self) -> None:
        """测试没有异常时不添加 exception 字段."""
        record = {
            "record": {
                "time": datetime(2025, 1, 11, 12, 0, 0),
                "level": type("Level", (), {"name": "INFO"})(),
                "name": "test",
                "function": "test",
                "line": 1,
                "message": "Normal message",
                "exception": None,
            },
            "extra": {},
        }

        result = _json_formatter(record)
        log_entry = json.loads(result)

        assert "exception" not in log_entry


class TestJSONFormatterSerialization:
    """测试 JSON 序列化."""

    def test_ensure_ascii_false(self) -> None:
        """测试中文字符不被转义."""
        record = {
            "record": {
                "time": datetime(2025, 1, 11, 12, 0, 0),
                "level": type("Level", (), {"name": "INFO"})(),
                "name": "test",
                "function": "test",
                "line": 1,
                "message": "测试中文消息",
                "exception": None,
            },
            "extra": {"event": "数据读取"},
        }

        result = _json_formatter(record)

        # [REVIEW] \uXXXX
        assert "测试中文消息" in result
        assert "数据读取" in result
        assert "\\u" not in result

    def test_valid_json(self) -> None:
        """测试输出是有效的 JSON."""
        record = {
            "record": {
                "time": datetime(2025, 1, 11, 12, 0, 0),
                "level": type("Level", (), {"name": "INFO"})(),
                "name": "test",
                "function": "test",
                "line": 1,
                "message": "Test",
                "exception": None,
            },
            "extra": {},
        }

        result = _json_formatter(record)

        # [REVIEW] JSON(去除换行符后)
        json.loads(result.rstrip("\n"))
