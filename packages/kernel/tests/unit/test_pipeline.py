"""ditto_kernel.pipeline 单元测试."""

from datetime import datetime
from typing import Any

from ditto_kernel.events import SimpleEventBus
from ditto_kernel.pipeline import Context, Pipeline, Stage
from ditto_kernel.provider import AnyFrame, BarQuery, InstrumentQuery

# ---------- 测试 Stub（不放 conftest） ----------


class StubClock:
    """测试用 Clock."""

    def __init__(self, initial: datetime) -> None:
        self._current = initial

    def now(self) -> datetime:
        return self._current

    def today(self):

        return self._current.date()

    def advance_to(self, target: datetime) -> None:
        self._current = target


class StubDataProvider:
    """测试用 DataProvider."""

    def get_bars(self, query: BarQuery) -> AnyFrame:
        return None

    def get_instruments(self, query: InstrumentQuery) -> AnyFrame:
        return None

    def get_schedule(self, start: str, end: str) -> AnyFrame:
        return None

    def get_factor(
        self,
        name: str,
        instruments: tuple[str, ...],
        start: str,
        end: str,
    ) -> AnyFrame:
        return None


# ---------- 测试 ----------


class TestContext:
    """Context 值对象测试."""

    def test_creation(self) -> None:
        """应正确创建 Context."""
        clock = StubClock(datetime(2024, 1, 1))
        provider = StubDataProvider()
        events = SimpleEventBus()
        ctx = Context(clock=clock, provider=provider, events=events)
        assert ctx.clock is clock
        assert ctx.provider is provider
        assert ctx.events is events

    def test_metadata_default(self) -> None:
        """metadata 默认为空 dict."""
        ctx = Context(
            clock=StubClock(datetime(2024, 1, 1)),
            provider=StubDataProvider(),
            events=SimpleEventBus(),
        )
        assert ctx.metadata == {}

    def test_metadata_custom(self) -> None:
        """应接受自定义 metadata."""
        ctx = Context(
            clock=StubClock(datetime(2024, 1, 1)),
            provider=StubDataProvider(),
            events=SimpleEventBus(),
            metadata={"run_id": "test-001"},
        )
        assert ctx.metadata == {"run_id": "test-001"}

    def test_frozen(self) -> None:
        """Context 应为不可变."""
        ctx = Context(
            clock=StubClock(datetime(2024, 1, 1)),
            provider=StubDataProvider(),
            events=SimpleEventBus(),
        )
        try:
            ctx.metadata = {"new": "value"}  # type: ignore[misc]
            msg = "应为 frozen"
            raise AssertionError(msg)
        except AttributeError:
            pass


class TestStage:
    """Stage Protocol 测试."""

    def test_custom_stage_satisfies_protocol(self) -> None:
        """自定义 Stage 应满足 Protocol."""

        class DoubleStage:
            @property
            def name(self) -> str:
                return "double"

            def process(self, data: Any, ctx: Context) -> Any:
                return data * 2

        stage: Stage = DoubleStage()
        assert stage.name == "double"
        assert stage.process(5, None) == 10  # type: ignore[arg-type]


class TestPipeline:
    """Pipeline 测试."""

    def _make_ctx(self) -> Context:
        return Context(
            clock=StubClock(datetime(2024, 1, 1)),
            provider=StubDataProvider(),
            events=SimpleEventBus(),
        )

    def test_empty_pipeline(self) -> None:
        """空 Pipeline 应返回原始输入."""
        pipeline = Pipeline()
        ctx = self._make_ctx()
        result = pipeline.execute(42, ctx)
        assert result == 42

    def test_single_stage(self) -> None:
        """单 stage Pipeline 应执行该 stage."""

        class AddOne:
            @property
            def name(self) -> str:
                return "add_one"

            def process(self, data: Any, ctx: Context) -> Any:
                return data + 1

        pipeline = Pipeline().add_stage(AddOne())
        ctx = self._make_ctx()
        assert pipeline.execute(10, ctx) == 11

    def test_multiple_stages(self) -> None:
        """多 stage Pipeline 应按序执行."""

        class AddOne:
            @property
            def name(self) -> str:
                return "add_one"

            def process(self, data: Any, ctx: Context) -> Any:
                return data + 1

        class Double:
            @property
            def name(self) -> str:
                return "double"

            def process(self, data: Any, ctx: Context) -> Any:
                return data * 2

        # add_one(5) = 6 -> double(6) = 12
        pipeline = Pipeline().add_stage(AddOne()).add_stage(Double())
        ctx = self._make_ctx()
        assert pipeline.execute(5, ctx) == 12

    def test_add_stage_returns_new_pipeline(self) -> None:
        """add_stage 应返回新 Pipeline（不可变）."""

        class Noop:
            @property
            def name(self) -> str:
                return "noop"

            def process(self, data: Any, ctx: Context) -> Any:
                return data

        original = Pipeline()
        extended = original.add_stage(Noop())
        assert original is not extended
        assert len(original._stages) == 0
        assert len(extended._stages) == 1

    def test_pipeline_with_context_access(self) -> None:
        """Stage 应能访问 Context."""

        class ReadClock:
            @property
            def name(self) -> str:
                return "read_clock"

            def process(self, data: Any, ctx: Context) -> Any:
                return ctx.clock.now()

        pipeline = Pipeline().add_stage(ReadClock())
        ctx = self._make_ctx()
        result = pipeline.execute(None, ctx)
        assert result == datetime(2024, 1, 1)
