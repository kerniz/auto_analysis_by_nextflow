"""Tests for Pipeline Event System"""


import pytest

from core.events import (
    ALL_STAGES,
    STAGE_LABELS,
    STAGE_PUBMED,
    EventType,
    PipelineEvent,
    PipelineEventBus,
)


class TestEventType:
    def test_all_event_types(self):
        assert len(EventType) == 8
        assert EventType.PIPELINE_START.value == "pipeline_start"
        assert EventType.PMID_STAGE_ERROR.value == "pmid_stage_error"

    def test_stage_labels_all_present(self):
        for stage in ALL_STAGES:
            assert stage in STAGE_LABELS


class TestPipelineEvent:
    def test_create_event(self):
        event = PipelineEvent(
            event_type=EventType.PMID_STAGE_START,
            pmid="12345",
            stage=STAGE_PUBMED,
        )
        assert event.pmid == "12345"
        assert event.stage == "pubmed"
        assert event.timestamp is not None

    def test_to_dict(self):
        event = PipelineEvent(
            event_type=EventType.PIPELINE_START,
            message="test",
            data={"count": 3},
        )
        d = event.to_dict()
        assert d["event_type"] == "pipeline_start"
        assert d["message"] == "test"
        assert d["data"]["count"] == 3
        assert "timestamp" in d

    def test_defaults(self):
        event = PipelineEvent(event_type=EventType.LOG_MESSAGE)
        assert event.pmid == ""
        assert event.stage == ""
        assert event.data == {}
        assert event.message == ""


class TestPipelineEventBus:
    def test_subscribe_and_emit(self):
        bus = PipelineEventBus()
        received = []
        bus.subscribe(lambda e: received.append(e))

        event = PipelineEvent(
            event_type=EventType.PIPELINE_START, message="go",
        )
        bus.emit(event)

        assert len(received) == 1
        assert received[0].message == "go"

    def test_multiple_listeners(self):
        bus = PipelineEventBus()
        results_a = []
        results_b = []
        bus.subscribe(lambda e: results_a.append(e))
        bus.subscribe(lambda e: results_b.append(e))

        bus.emit(PipelineEvent(event_type=EventType.LOG_MESSAGE))
        assert len(results_a) == 1
        assert len(results_b) == 1

    def test_unsubscribe(self):
        bus = PipelineEventBus()
        received = []
        cb = lambda e: received.append(e)  # noqa: E731
        bus.subscribe(cb)
        bus.unsubscribe(cb)

        bus.emit(PipelineEvent(event_type=EventType.LOG_MESSAGE))
        assert len(received) == 0

    def test_listener_count(self):
        bus = PipelineEventBus()
        assert bus.listener_count == 0
        cb = lambda e: None  # noqa: E731
        bus.subscribe(cb)
        assert bus.listener_count == 1
        bus.unsubscribe(cb)
        assert bus.listener_count == 0

    def test_emit_exception_does_not_propagate(self):
        bus = PipelineEventBus()
        bus.subscribe(lambda e: 1 / 0)  # will raise ZeroDivisionError
        received = []
        bus.subscribe(lambda e: received.append(e))

        # Should not raise
        bus.emit(PipelineEvent(event_type=EventType.LOG_MESSAGE))
        assert len(received) == 1

    def test_history(self):
        bus = PipelineEventBus()
        bus.emit(PipelineEvent(
            event_type=EventType.PMID_START, pmid="111",
        ))
        bus.emit(PipelineEvent(
            event_type=EventType.PMID_COMPLETE, pmid="111",
        ))

        assert len(bus.history) == 2
        assert bus.history[0].event_type == EventType.PMID_START
        assert bus.history[1].event_type == EventType.PMID_COMPLETE

    def test_clear_history(self):
        bus = PipelineEventBus()
        bus.emit(PipelineEvent(event_type=EventType.LOG_MESSAGE))
        bus.clear_history()
        assert len(bus.history) == 0

    def test_history_limit(self):
        bus = PipelineEventBus()
        bus._max_history = 5
        for i in range(10):
            bus.emit(PipelineEvent(
                event_type=EventType.LOG_MESSAGE, message=str(i),
            ))
        assert len(bus.history) == 5
        assert bus.history[0].message == "5"

    @pytest.mark.asyncio
    async def test_emit_async(self):
        bus = PipelineEventBus()
        received = []
        bus.subscribe(lambda e: received.append(e))

        await bus.emit_async(PipelineEvent(
            event_type=EventType.PIPELINE_COMPLETE,
        ))
        assert len(received) == 1

    @pytest.mark.asyncio
    async def test_emit_async_with_coroutine_listener(self):
        bus = PipelineEventBus()
        received = []

        async def async_listener(event):
            received.append(event)

        bus.subscribe(async_listener)
        await bus.emit_async(PipelineEvent(
            event_type=EventType.PMID_START, pmid="999",
        ))
        assert len(received) == 1
        assert received[0].pmid == "999"

    @pytest.mark.asyncio
    async def test_emit_async_exception_does_not_propagate(self):
        bus = PipelineEventBus()

        async def bad_listener(event):
            raise RuntimeError("boom")

        received = []
        bus.subscribe(bad_listener)
        bus.subscribe(lambda e: received.append(e))

        await bus.emit_async(PipelineEvent(
            event_type=EventType.LOG_MESSAGE,
        ))
        assert len(received) == 1
