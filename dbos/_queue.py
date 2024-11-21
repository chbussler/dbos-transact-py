import threading
import traceback
from typing import TYPE_CHECKING, Optional, TypedDict

from ._core import P, R, execute_workflow_by_id, start_workflow

if TYPE_CHECKING:
    from ._dbos import DBOS, Workflow, WorkflowHandle


class QueueRateLimit(TypedDict):
    """
    Limit the maximum number of workflows from this queue that can be started in a given period.

    If the limit is 5 and the period is 10, no more than 5 functions can be
    started per 10 seconds.
    """

    limit: int
    period: float


class Queue:
    """
    Workflow queue.

    Workflow queues allow workflows to be started at a later time, based on concurrency and
    rate limits.
    """

    def __init__(
        self,
        name: str,
        concurrency: Optional[int] = None,
        limiter: Optional[QueueRateLimit] = None,
    ) -> None:
        self.name = name
        self.concurrency = concurrency
        self.limiter = limiter
        from ._dbos import _get_or_create_dbos_registry

        registry = _get_or_create_dbos_registry()
        registry.queue_info_map[self.name] = self

    def enqueue(
        self, func: "Workflow[P, R]", *args: P.args, **kwargs: P.kwargs
    ) -> "WorkflowHandle[R]":
        from ._dbos import _get_dbos_instance

        dbos = _get_dbos_instance()
        return start_workflow(dbos, func, self.name, False, *args, **kwargs)


def _queue_thread(stop_event: threading.Event, dbos: "DBOS") -> None:
    while not stop_event.is_set():
        if stop_event.wait(timeout=1):
            return
        for _, queue in dbos._registry.queue_info_map.items():
            try:
                wf_ids = dbos._sys_db.start_queued_workflows(queue)
                for id in wf_ids:
                    execute_workflow_by_id(dbos, id)
            except Exception:
                dbos.logger.warning(
                    f"Exception encountered in queue thread: {traceback.format_exc()}"
                )