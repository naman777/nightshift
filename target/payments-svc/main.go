// payments-svc: the payments API. In compose it is reached through Toxiproxy so latency/drops are injectable.
//
// Fault hooks: handler_timeout_ms / log_level (config/payments-svc.yaml), retain_receipts flag (memory leak).
package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"math/rand"
	"net/http"
	"os"
	"sync"
	"time"

	"nightshift/target/internal/kv"
	"nightshift/target/internal/obs"
)

var version = "dev" // -X main.version=<git sha>

var (
	mu       sync.Mutex
	receipts [][]byte
)

func env(k, d string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return d
}

func main() {
	cfg := kv.New(env("CONFIG_FILE", "/config/payments-svc.yaml"))
	flags := kv.NewJSON(env("FLAGS_FILE", "/config/flags.json"))
	reg := obs.New()
	reg.RegisterProcess()
	log := obs.NewLogger("payments-svc", "payments-svc-1", func() string { return cfg.Str("log_level", "info") }, reg)

	charge := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if flags.Bool("retain_receipts", false) {
			mu.Lock()
			receipts = append(receipts, bytes.Repeat([]byte{2}, 256<<10))
			mu.Unlock()
		}
		work := time.Duration(20+rand.Intn(40)) * time.Millisecond
		time.Sleep(work)
		limit := time.Duration(cfg.Int("handler_timeout_ms", 2000)) * time.Millisecond
		if work > limit {
			log.Errorf("handler exceeded handler_timeout_ms=%d: returning 504 for /charge", limit.Milliseconds())
			http.Error(w, "timeout", http.StatusGatewayTimeout)
			return
		}
		log.Infof("request handled path=/charge status=200 latency=%dms", work.Milliseconds())
		fmt.Fprintln(w, `{"status":"charged"}`)
	})

	mux := http.NewServeMux()
	mux.Handle("/charge", obs.Middleware(reg, log, "/charge", charge))
	mux.HandleFunc("/healthz", func(w http.ResponseWriter, _ *http.Request) { fmt.Fprintln(w, "ok") })
	mux.HandleFunc("/version", func(w http.ResponseWriter, _ *http.Request) {
		json.NewEncoder(w).Encode(map[string]string{"service": "payments-svc", "sha": version})
	})
	mux.Handle("/metrics", reg.Handler())
	log.Infof("payments-svc starting version=%s", version)
	if err := http.ListenAndServe(":8082", mux); err != nil {
		log.Errorf("listen: %v", err)
	}
}
