"""Concurrent use of one model from several threads (script a12).

The DLL is a single global model + stateful HDF handles: ctypes releases
the GIL around every call, so four threads hammering the same getters
either crash the process, wedge a worker, or hand back mixed-up numbers.
Expected: no crash, no stuck thread, and identical answers per query.
"""
from __future__ import annotations

import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import GW_BUDGET, GW_HYD, attempt, main, open_model  # noqa: E402

N_THREADS = 4
JOIN_TIMEOUT = 90


def _run(worker):
    errs, res = [], []

    def w(i):
        try:
            worker(i, res)
        except BaseException as ex:      # noqa: BLE001 — recorded, not raised
            errs.append([i, type(ex).__name__, str(ex)[:120]])
    ts = [threading.Thread(target=w, args=(i,), daemon=True) for i in range(N_THREADS)]
    for t in ts:
        t.start()
    for t in ts:
        t.join(JOIN_TIMEOUT)
    return {"n_results": len(res), "errors": errs[:5], "n_errors": len(errs),
            "alive": [t.is_alive() for t in ts]}, res


def case_threads_nodes_elements(model_dir):
    m = open_model(model_dir)

    def worker(i, res):
        for _ in range(20):
            df = m.nodes_df()
            m._cache.clear()
            x = m.get_node_coordinates()[0]
            e = m.elements_df()
            m._cache.clear()
            res.append((i, list(df.shape), list(e.shape), float(x.sum())))

    def go():
        summary, res = _run(worker)
        summary["distinct_xsum"] = len({r[3] for r in res})
        summary["distinct_shapes"] = len({(tuple(r[1]), tuple(r[2])) for r in res})
        return summary
    return attempt(go)


def case_threads_heads(model_dir):
    m = open_model(model_dir)

    def worker(i, res):
        for _ in range(5):
            layer = 1 + (i % 2)
            df = m.heads_df(layer)
            res.append((layer, list(df.shape), round(float(df.values.mean()), 6)))

    def go():
        summary, res = _run(worker)
        per = {}
        for layer, _sh, mn in res:
            per.setdefault(str(layer), set()).add(mn)
        summary["distinct_means_per_layer"] = {k: len(v) for k, v in per.items()}
        return summary
    return attempt(go)


def case_threads_budget_hydrograph(model_dir):
    m = open_model(model_dir)

    def worker(i, res):
        for _ in range(5):
            if i % 2:
                df = m.budget_df(GW_BUDGET, 1 + (i // 2) % 2)
            else:
                df = m.hydrograph_df(GW_HYD, 1 + i, 1)
            res.append((i, list(df.shape), round(float(df.values.mean()), 6)))

    def go():
        summary, res = _run(worker)
        per = {}
        for i, _sh, mn in res:
            per.setdefault(str(i), set()).add(mn)
        summary["distinct_means_per_thread"] = {k: len(v) for k, v in per.items()}
        return summary
    return attempt(go)


if __name__ == "__main__":
    main(globals())
