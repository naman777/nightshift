from __future__ import annotations

from agents.core.models import Category

from .base import Fault, deploy_commit

BUGS = {
    "n_plus_one": dict(
        message="orders: load line items inline for list view",
        diff=("--- a/handlers/orders.go\n+++ b/handlers/orders.go\n@@ -14,9 +14,12 @@\n"
              "-\titems, err := h.loadItemsBatch(orders) // single query: WHERE order_id = ANY($1)\n"
              "+\tvar items []Item\n+\tfor _, o := range orders {\n"
              "+\t\tit, err := h.loadItems(o.ID) // one query per order\n+\t\tif err != nil { http.Error(w, \"db error\", 500); return }\n"
              "+\t\titems = append(items, it...)\n+\t}\n"),
        patch=("\titems, err := h.loadItemsBatch(orders) // single query: WHERE order_id = ANY($1)",
               "\tvar items []Item\n\tfor _, o := range orders {\n\t\tit, err := h.loadItems(o.ID) // one query per order\n"
               "\t\tif err != nil { http.Error(w, \"db error\", 500); return }\n\t\titems = append(items, it...)\n\t}\n\tvar err error"),
        tests=(True, "ok  \torders-svc/...\t0.421s"),
    ),
    "nil_deref": dict(
        message="orders: show default shipping address in summary",
        diff=("--- a/handlers/orders.go\n+++ b/handlers/orders.go\n@@ -20,3 +20,4 @@\n"
              "+\taddr := orders[0].Customer.Address // orders may be empty\n+\t_ = addr.Line1\n"),
        patch=("\twriteJSON(w, orders, items)", "\taddr := orders[0].Customer.Address // orders may be empty\n\t_ = addr.Line1\n\twriteJSON(w, orders, items)"),
        tests=(False, "--- FAIL: TestListOrdersEmptyCustomer (0.00s)\n    panic: runtime error: invalid memory address or nil pointer dereference\nFAIL\torders-svc/handlers\t0.031s"),
    ),
    "missing_index": dict(
        message="orders: filter list by status",
        diff=("--- a/handlers/orders.go\n+++ b/handlers/orders.go\n@@ -8,1 +8,1 @@\n"
              "-\trows, err := h.db.Query(\"SELECT id, customer_id FROM orders WHERE customer_id = $1 LIMIT 50\", customerID(r))\n"
              "+\trows, err := h.db.Query(\"SELECT id, customer_id FROM orders WHERE status <> 'archived' ORDER BY created_at DESC LIMIT 50\")\n"),
        patch=("WHERE customer_id = $1 LIMIT 50\", customerID(r))", "WHERE status <> 'archived' ORDER BY created_at DESC LIMIT 50\")"),
        tests=(True, "ok  \torders-svc/...\t0.398s"),
    ),
    "index_out_of_range": dict(
        message="orders: pick primary item for receipt",
        diff=("--- a/handlers/orders.go\n+++ b/handlers/orders.go\n@@ -20,3 +20,4 @@\n+\tprimary := items[0]\n"),
        patch=("\twriteJSON(w, orders, items)", "\tprimary := items[0]\n\t_ = primary\n\twriteJSON(w, orders, items)"),
        tests=(False, "--- FAIL: TestListOrdersNoItems (0.00s)\n    panic: runtime error: index out of range [0] with length 0\nFAIL\torders-svc/handlers\t0.028s"),
    ),
}


class BadDeploy(Fault):
    def apply_sim(self, w, params, t_f):
        p = self.merged(params)
        bug = BUGS[p["bug"]]
        c = deploy_commit(w, t_f - 30, p["service"], bug["message"], ["handlers/orders.go"], bug["diff"])
        w.facts.update(sha=c.sha, bug=p["bug"], deploy_service=p["service"])
        old, new = bug["patch"]
        w.code["handlers/orders.go"] = w.code["handlers/orders.go"].replace(old, new)
        w.test_result = {"passed": bug["tests"][0], "output": bug["tests"][1]}
        svc = p["service"]
        if p["bug"] == "n_plus_one":
            w.alert_name = "HighLatency_orders"
            w.add_effect("p99_latency_seconds", svc, t_f, "mult", 9, 30)
            w.add_effect("db_connections_in_use", svc, t_f, "mult", 2.6, 30)
            w.add_effect("cpu_ratio", svc, t_f, "mult", 1.6, 30)
            w.add_log(svc, "warn", "slow query: SELECT * FROM line_items WHERE order_id = $1 took {ms}ms (executed 50x in one request)",
                      t_f, every_s=3, ms_base=40)
        elif p["bug"] == "missing_index":
            w.alert_name = "HighLatency_orders"
            w.add_effect("p99_latency_seconds", svc, t_f, "mult", 7, 30)
            w.add_effect("cpu_ratio", svc, t_f, "mult", 1.8, 30)
            w.add_log(svc, "warn", "slow query: seq scan on orders took {ms}ms (rows examined: 2.1M)", t_f, every_s=3, ms_base=1400)
        else:
            w.alert_name = "HighErrorRate_orders"
            w.add_effect("error_rate", svc, t_f, "mult", 70, 20)
            w.add_effect("error_rate", "lb", t_f, "mult", 50, 20)
            msg = ("panic: runtime error: invalid memory address or nil pointer dereference in handlers.(*Handler).ListOrders"
                   if p["bug"] == "nil_deref" else
                   "panic: runtime error: index out of range [0] with length 0 in handlers.(*Handler).ListOrders")
            w.add_log(svc, "error", msg, t_f, every_s=2)
        w.alert_service = svc

    def live_steps(self, params):
        p = self.merged(params)
        return [{"do": "deploy", "service": p["service"], "bug": p["bug"]}]


FAULT = BadDeploy("bad_deploy", "HighErrorRate_orders", Category.BAD_DEPLOY, {"service": "orders-svc", "bug": "n_plus_one"},
                  "A build with a bug ships and is recorded in the deploy log.")
