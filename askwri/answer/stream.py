"""Keep an answer stream alive: run the blocking pipeline in a thread and fill silences with pings."""

import logging
import queue
import threading
from collections.abc import Iterator

from askwri.models import ModelError

log = logging.getLogger(__name__)

PING_SECONDS = 15
_DONE = object()


def stream_with_pings(
    events: Iterator[dict], *, ping_seconds: float = PING_SECONDS
) -> Iterator[dict]:
    """Yield `events` as a worker thread produces them, plus a `ping` after each silence.

    CloudFront drops a stream after 30 idle seconds, and one model call or a cold Aurora query
    can take longer than 15. An exception ends the stream with one `error` event naming the
    failed step, and is logged with its traceback.
    """
    items: queue.Queue = queue.Queue()

    def produce() -> None:
        try:
            for event in events:
                items.put(event)
        # Any failure must end the stream with an error event; it is logged where it's taken off.
        except Exception as error:  # noqa: BLE001
            items.put(error)
        items.put(_DONE)

    # shortcut: daemon thread, not cancelled - if the client disconnects, the run finishes
    # its current call and the result is discarded.
    threading.Thread(target=produce, daemon=True).start()
    step = None
    while True:
        try:
            item = items.get(timeout=ping_seconds)
        except queue.Empty:
            yield {"type": "ping"}
            continue
        if item is _DONE:
            return
        if isinstance(item, Exception):
            log.error("Answer failed during step %s", step, exc_info=item)
            yield {"type": "error", "message": error_message(item, step)}
            return
        if item["type"] == "step" and item["status"] == "now":
            step = item["id"]
        yield item


def error_message(error: Exception, step: str | None) -> str:
    """What the user sees when a step fails; details stay in the logs."""
    if isinstance(error, ModelError):
        return "The model call failed"
    if step and step.startswith("search"):
        return "The search failed"
    return "Something went wrong"
