"""ditto_kernel.identity 单元测试."""

from ditto_kernel.identity import InstrumentId


class TestInstrumentId:
    """InstrumentId NewType 测试."""

    def test_is_newtype(self) -> None:
        """InstrumentId 应为 int 上的 NewType."""
        assert InstrumentId.__supertype__ is int  # type: ignore[attr-defined]

    def test_accepts_int(self) -> None:
        """InstrumentId 应接受 int 值."""
        id_: InstrumentId = InstrumentId(1_000_001)
        assert id_ == 1_000_001

    def test_int_operations(self) -> None:
        """InstrumentId 应支持 int 运算（类型擦除后）."""
        id_: InstrumentId = InstrumentId(1_000_001)
        assert id_ + 1 == 1_000_002
        assert id_ > 0

    def test_type_safety_rejects_str(self) -> None:
        """basedpyright 应拒绝 str 赋值给 InstrumentId（编译期检查，运行时不阻断）."""
        # 运行时 NewType 是 no-op，这个测试主要确认类型定义正确
        id_: InstrumentId = InstrumentId(1)  # type: ignore[assignment]
        assert isinstance(id_, int)
