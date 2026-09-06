"""定期実行パイプラインの進捗記録(pipeline/pipeline_store)のテスト。"""

from __future__ import annotations

from pipeline import pipeline_store as pstore


def test_create_run_makes_pending_steps(db_session):
    run_id = pstore.create_run()
    run = pstore.get_run(run_id)
    assert run["status"] == "running"
    keys = [s["step_key"] for s in run["steps"]]
    assert keys == [k for k, _, _ in pstore.STEPS]
    assert all(s["status"] == "pending" for s in run["steps"])
    assert {s["phase"] for s in run["steps"]} == {"parallel", "sequential"}
    assert pstore.running_run_id() == run_id


def test_set_step_and_finish(db_session):
    run_id = pstore.create_run()

    pstore.set_step(run_id, "design", "running", started=True)
    pstore.set_step(run_id, "design", "success",
                    result={"run_id": 7, "feature_count": 4}, finished=True)
    pstore.set_step(run_id, "spec_diff", "running", started=True)
    pstore.set_step(run_id, "spec_diff", "error", error="材料が足りません", finished=True)

    run = pstore.get_run(run_id)
    st = {s["step_key"]: s for s in run["steps"]}
    assert st["design"]["status"] == "success"
    assert st["design"]["result"]["feature_count"] == 4
    assert st["design"]["duration_sec"] is not None
    assert st["spec_diff"]["status"] == "error" and "足りません" in st["spec_diff"]["error"]
    assert st["mattermost"]["status"] == "pending"

    pstore.finish_run(run_id, "error")
    run = pstore.get_run(run_id)
    assert run["status"] == "error" and run["finished_at"] is not None
    assert pstore.running_run_id() is None


def test_list_runs_counts(db_session):
    run_id = pstore.create_run()
    pstore.set_step(run_id, "design", "success", finished=True)
    pstore.set_step(run_id, "code", "success", finished=True)
    pstore.set_step(run_id, "github", "error", error="x", finished=True)
    pstore.finish_run(run_id, "error")

    rows = pstore.list_runs()
    assert rows and rows[0]["id"] == run_id
    assert rows[0]["success_steps"] == 2 and rows[0]["error_steps"] == 1
    assert rows[0]["total_steps"] == len(pstore.STEPS)
