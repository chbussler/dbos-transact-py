import os
import time
import uuid

import requests

from dbos_transact import DBOS
from dbos_transact.communicator import CommunicatorContext
from dbos_transact.transaction import TransactionContext
from dbos_transact.workflow import WorkflowContext


def test_admin_endpoints(dbos: DBOS) -> None:

    # Test GET /dbos-healthz
    response = requests.get("http://localhost:3001/dbos-healthz", timeout=5)
    assert response.status_code == 200
    assert response.text == "healthy"

    # Test POST /dbos-workflow-recovery
    data = ["executor1", "executor2"]
    response = requests.post(
        "http://localhost:3001/dbos-workflow-recovery", json=data, timeout=5
    )
    assert response.status_code == 200
    assert response.json() == []

    # Test GET not found
    response = requests.get("http://localhost:3001/stuff", timeout=5)
    assert response.status_code == 404

    # Test POST not found
    response = requests.post("http://localhost:3001/stuff", timeout=5)
    assert response.status_code == 404


def test_admin_recovery(dbos: DBOS) -> None:
    os.environ["DBOS__VMID"] = "testexecutor"
    os.environ["DBOS__APPVERSION"] = "testversion"
    os.environ["DBOS__APPID"] = "testappid"

    comm_counter: int = 0
    wf_counter: int = 0

    @dbos.workflow()
    def test_workflow(ctx: WorkflowContext, var: str, var2: str) -> str:
        nonlocal wf_counter
        wf_counter += 1
        res = test_communicator(ctx.comm_ctx(), var2)
        return res + var

    @dbos.communicator()
    def test_communicator(ctx: CommunicatorContext, var2: str) -> str:
        nonlocal comm_counter
        comm_counter += 1
        return var2 + "1"

    wfuuid = str(uuid.uuid4())
    assert test_workflow(dbos.wf_ctx(wfuuid), "bob", "bob") == "bob1bob"

    # Change the workflow status to pending
    dbos.sys_db.update_workflow_status(
        {
            "workflow_uuid": wfuuid,
            "status": "PENDING",
            "name": test_workflow.__qualname__,
            "output": None,
            "error": None,
            "executor_id": None,
            "app_id": None,
            "app_version": None,
        }
    )
    status = dbos.sys_db.get_workflow_status(wfuuid)
    assert (
        status is not None and status["status"] == "PENDING"
    ), "Workflow status not updated"

    # Test POST /dbos-workflow-recovery
    data = ["testexecutor"]
    response = requests.post(
        "http://localhost:3001/dbos-workflow-recovery", json=data, timeout=5
    )
    assert response.status_code == 200
    assert response.json() == [wfuuid]

    # Wait until the workflow is recovered
    max_retries = 10
    succeeded = False
    for attempt in range(max_retries):
        status = dbos.sys_db.get_workflow_status(wfuuid)
        if status is not None and status["status"] == "SUCCESS":
            succeeded = True
            break
        else:
            time.sleep(1)
            print(f"Attempt {attempt + 1} failed. Retrying in 1 second...")
    assert succeeded, "Workflow did not recover"