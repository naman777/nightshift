// orders-svc: the order API. Postgres-backed, calls payments-svc for charges.
//
// Fault hooks (all real, driven by config/flags/build args so the chaos CLI can trigger them):
//   - request_timeout_ms / payments_timeout_ms / db_pool_size / log_level   (config/orders-svc.yaml, hot reloaded)
//   - enable_unbounded_cache / enable_session_cache / enable_prefetch flags  (config/flags.json)  -> memory leak
//   - -X main.bug=n_plus_one|nil_deref|missing_index|index_out_of_range      (a "bad deploy" build)
package main

import (
	"bytes"
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"math/rand"
	"net/http"
	"os"
	"strconv"
	"sync"
	"time"

	_ "github.com/lib/pq"

	"nightshift/target/internal/kv"
	"nightshift/target/internal/obs"
)

var (
	version = "dev" // -X main.version=<git sha>
	bug     = ""    // -X main.bug=<bug name>
)

type server struct {
	db      *sql.DB
	cfg     *kv.Store
	flags   *kv.Store
	log     *obs.Logger
	reg     *obs.Registry
	payURL  string
	client  *http.Client
	cacheMu sync.Mutex
	cache   [][]byte
}

func env(k, d string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return d
}

func main() {
	replica := env("REPLICA", "orders-svc-1")
	cfg := kv.New(env("CONFIG_FILE", "/config/orders-svc.yaml"))
	flags := kv.NewJSON(env("FLAGS_FILE", "/config/flags.json"))
	reg := obs.New()
	reg.RegisterProcess()
	log := obs.NewLogger("orders-svc", replica, func() string { return cfg.Str("log_level", "info") }, reg)

	db, err := sql.Open("postgres", env("DATABASE_URL", "postgres://nightshift:nightshift@postgres:5432/orders?sslmode=disable"))
	if err != nil {
		log.Errorf("open db: %v", err)
		os.Exit(1)
	}
	db.SetMaxOpenConns(cfg.Int("db_pool_size", 20))
	go func() { // db_pool_size is hot reloaded
		for {
			time.Sleep(2 * time.Second)
			db.SetMaxOpenConns(cfg.Int("db_pool_size", 20))
		}
	}()
	reg.GaugeFunc("db_connections_in_use", "", func() float64 { return float64(db.Stats().InUse) })

	s := &server{db: db, cfg: cfg, flags: flags, log: log, reg: reg, payURL: env("PAYMENTS_URL", "http://toxiproxy:8081"),
		client: &http.Client{}}
	mux := http.NewServeMux()
	mux.Handle("/orders", obs.Middleware(reg, log, "/orders", http.HandlerFunc(s.orders)))
	mux.HandleFunc("/healthz", func(w http.ResponseWriter, _ *http.Request) { fmt.Fprintln(w, "ok") })
	mux.HandleFunc("/version", func(w http.ResponseWriter, _ *http.Request) {
		json.NewEncoder(w).Encode(map[string]string{"service": "orders-svc", "replica": replica, "sha": version, "bug": bug})
	})
	mux.Handle("/metrics", reg.Handler())
	log.Infof("orders-svc %s starting version=%s bug=%q", replica, version, bug)
	if err := http.ListenAndServe(":8080", mux); err != nil {
		log.Errorf("listen: %v", err)
	}
}

func (s *server) leak() {
	if s.flags.Bool("enable_unbounded_cache", false) || s.flags.Bool("enable_session_cache", false) || s.flags.Bool("enable_prefetch", false) {
		s.cacheMu.Lock()
		s.cache = append(s.cache, bytes.Repeat([]byte{1}, 256<<10)) // never evicted
		n := len(s.cache)
		s.cacheMu.Unlock()
		if n%20 == 0 {
			s.log.Warnf("cache size=%d00000 entries (unbounded); evictions=0", n)
		}
	}
}

func (s *server) orders(w http.ResponseWriter, r *http.Request) {
	s.leak()
	timeout := time.Duration(s.cfg.Int("request_timeout_ms", 3000)) * time.Millisecond
	ctx, cancel := context.WithTimeout(r.Context(), timeout)
	defer cancel()
	if s.cfg.Str("log_level", "info") == "debug" {
		for i := 0; i < 20; i++ { // hot-path debug logging: the log flood fault
			s.log.Debugf("cache lookup key=order:%d hit=false layer=l2 (%dus)", rand.Intn(100000), rand.Intn(90))
		}
	}
	if r.Method == http.MethodPost {
		s.create(ctx, w)
		return
	}
	cust := rand.Intn(200) + 1
	if v := r.URL.Query().Get("customer"); v != "" {
		cust, _ = strconv.Atoi(v)
	}
	type order struct {
		ID    int
		Items []int
	}
	var query string
	var args []interface{}
	switch bug {
	case "missing_index":
		query, args = "SELECT pg_sleep(0.35), id FROM orders WHERE status <> 'archived' ORDER BY created_at DESC LIMIT 50", nil
	default:
		query, args = "SELECT 0, id FROM orders WHERE customer_id = $1 LIMIT 50", []interface{}{cust}
	}
	rows, err := s.db.QueryContext(ctx, query, args...)
	if err != nil {
		s.fail(w, err, timeout)
		return
	}
	var orders []order
	for rows.Next() {
		var pad interface{}
		var o order
		if err := rows.Scan(&pad, &o.ID); err == nil {
			orders = append(orders, o)
		}
	}
	rows.Close()

	switch bug {
	case "n_plus_one":
		for i := range orders {
			s.slowItems(ctx, &orders[i].Items, orders[i].ID)
		}
	case "nil_deref":
		var first *order
		if len(orders) > 0 {
			first = &orders[0]
		}
		_ = first.ID // panics when the customer has no orders
	case "index_out_of_range":
		var ids []int
		_ = ids[0] // panics: index out of range [0] with length 0
	default:
		var n int // single batched query for all line items (the healthy code path)
		s.db.QueryRowContext(ctx, "SELECT count(*) FROM line_items li JOIN orders o ON o.id = li.order_id WHERE o.customer_id = $1", cust).Scan(&n)
	}
	json.NewEncoder(w).Encode(map[string]interface{}{"customer": cust, "orders": len(orders)})
}

func (s *server) slowItems(ctx context.Context, out *[]int, orderID int) {
	start := time.Now()
	rows, err := s.db.QueryContext(ctx, "SELECT id FROM line_items WHERE order_id = $1", orderID)
	if err != nil {
		return
	}
	defer rows.Close()
	for rows.Next() {
		var id int
		rows.Scan(&id)
		*out = append(*out, id)
	}
	if ms := time.Since(start).Milliseconds(); ms > 20 {
		s.log.Warnf("slow query: SELECT * FROM line_items WHERE order_id = $1 took %dms (executed 50x in one request)", ms)
	}
}

func (s *server) create(ctx context.Context, w http.ResponseWriter) {
	pctx, cancel := context.WithTimeout(ctx, time.Duration(s.cfg.Int("payments_timeout_ms", 1500))*time.Millisecond)
	defer cancel()
	req, _ := http.NewRequestWithContext(pctx, http.MethodPost, s.payURL+"/charge", bytes.NewReader([]byte(`{"cents":1299}`)))
	start := time.Now()
	resp, err := s.client.Do(req)
	s.reg.Observe("dependency_latency_seconds", `dep="payments-svc"`, time.Since(start).Seconds())
	if err != nil {
		if time.Since(start) > 500*time.Millisecond {
			s.log.Warnf("call to payments-svc slow: %dms (path=/charge)", time.Since(start).Milliseconds())
		}
		s.log.Errorf("charge failed: %v", err)
		http.Error(w, "payment failed", http.StatusBadGateway)
		return
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 500 {
		s.log.Errorf("payments-svc returned %d for /charge", resp.StatusCode)
		http.Error(w, "payment failed", http.StatusBadGateway)
		return
	}
	if _, err := s.db.ExecContext(ctx, "INSERT INTO orders (customer_id, status) VALUES ($1, 'paid')", rand.Intn(150)+1); err != nil {
		s.fail(w, err, 0)
		return
	}
	w.WriteHeader(http.StatusCreated)
	fmt.Fprintln(w, `{"status":"created"}`)
}

func (s *server) fail(w http.ResponseWriter, err error, timeout time.Duration) {
	if err == context.DeadlineExceeded || (err != nil && err.Error() == "context deadline exceeded") {
		s.log.Errorf("context deadline exceeded after %dms handling /orders (request_timeout_ms=%d)", timeout.Milliseconds(), timeout.Milliseconds())
		http.Error(w, "timeout", http.StatusServiceUnavailable)
		return
	}
	s.log.Errorf("db error: %v", err)
	http.Error(w, "db error", http.StatusInternalServerError)
}
