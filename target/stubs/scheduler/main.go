// scheduler-stub: a stand-in for Foreman (the Go job scheduler) so the stack runs end to end today.
//
// Same contract the real Foreman will honour, so it can be dropped in as compose service "scheduler":
//
//	config/scheduler.yaml: worker_count, settlement_schedule ("*/N * * * *" or "0 H * * *")
//	metrics: queue_depth, process_cpu_seconds_total, db_connections_in_use, job_failures_total
//	POST /admin/jobs {"name","hold_connections","duration_s"}   (used by the chaos CLI to simulate a connection-hogging job)
package main

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"runtime"
	"strconv"
	"strings"
	"sync"
	"time"

	_ "github.com/lib/pq"

	"nightshift/target/internal/kv"
	"nightshift/target/internal/obs"
)

var version = "dev"

func env(k, d string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return d
}

// due reports whether a minimal cron expression matches t.
func due(expr string, t time.Time) bool {
	f := strings.Fields(expr)
	if len(f) < 2 {
		return false
	}
	if strings.HasPrefix(f[0], "*/") {
		n, err := strconv.Atoi(strings.TrimPrefix(f[0], "*/"))
		return err == nil && n > 0 && t.Minute()%n == 0
	}
	m, err1 := strconv.Atoi(f[0])
	h, err2 := strconv.Atoi(f[1])
	return err1 == nil && err2 == nil && t.Minute() == m && t.Hour() == h
}

func main() {
	cfg := kv.New(env("CONFIG_FILE", "/config/scheduler.yaml"))
	reg := obs.New()
	reg.RegisterProcess()
	log := obs.NewLogger("scheduler", "scheduler-1", func() string { return cfg.Str("log_level", "info") }, reg)

	db, err := sql.Open("postgres", env("DATABASE_URL", "postgres://nightshift:nightshift@postgres:5432/orders?sslmode=disable"))
	if err != nil {
		log.Errorf("open db: %v", err)
		os.Exit(1)
	}
	db.SetMaxOpenConns(4)
	reg.GaugeFunc("db_connections_in_use", "", func() float64 { return float64(db.Stats().InUse) })

	queue := make(chan int, 200000)
	reg.GaugeFunc("queue_depth", "", func() float64 { return float64(len(queue)) })

	// producer: steady stream of jobs
	go func() {
		id := 0
		for {
			time.Sleep(100 * time.Millisecond)
			for i := 0; i < cfg.Int("enqueue_per_100ms", 1); i++ {
				id++
				select {
				case queue <- id:
				default:
				}
			}
		}
	}()

	// worker pool, resized from config (worker_count)
	var mu sync.Mutex
	var stops []chan struct{}
	go func() {
		for {
			want := cfg.Int("worker_count", 8)
			mu.Lock()
			for len(stops) < want {
				stop := make(chan struct{})
				stops = append(stops, stop)
				go func() {
					for {
						select {
						case <-stop:
							return
						case <-queue:
							time.Sleep(400 * time.Millisecond) // one job
						}
					}
				}()
			}
			for len(stops) > want {
				close(stops[len(stops)-1])
				stops = stops[:len(stops)-1]
			}
			mu.Unlock()
			time.Sleep(2 * time.Second)
		}
	}()

	// settlement job: CPU-bound, runs on its cron schedule
	go func() {
		var last int
		for {
			time.Sleep(10 * time.Second)
			now := time.Now()
			if due(cfg.Str("settlement_schedule", "0 3 * * *"), now) && now.Minute() != last {
				last = now.Minute()
				log.Infof("job settlement batch=%d started (cpu-bound, schedule=%s)", now.Unix(), cfg.Str("settlement_schedule", ""))
				end := time.Now().Add(45 * time.Second)
				for i := 0; i < runtime.NumCPU(); i++ {
					go func() {
						x := 0
						for time.Now().Before(end) {
							x++
						}
						_ = x
					}()
				}
			}
		}
	}()

	mux := http.NewServeMux()
	mux.HandleFunc("/admin/jobs", func(w http.ResponseWriter, r *http.Request) {
		var req struct {
			Name            string `json:"name"`
			HoldConnections int    `json:"hold_connections"`
			DurationS       int    `json:"duration_s"`
		}
		if json.NewDecoder(r.Body).Decode(&req) != nil || req.HoldConnections <= 0 {
			http.Error(w, "bad request", http.StatusBadRequest)
			return
		}
		db.SetMaxOpenConns(req.HoldConnections + 4)
		go func() {
			var conns []*sql.Conn
			for i := 0; i < req.HoldConnections; i++ {
				c, err := db.Conn(context.Background())
				if err != nil {
					log.Errorf("job %s could not take a connection: %v", req.Name, err)
					break
				}
				conns = append(conns, c)
			}
			end := time.Now().Add(time.Duration(req.DurationS) * time.Second)
			for time.Now().Before(end) {
				log.Warnf("job %s holding %d db connections; transaction open for %dms", req.Name, len(conns), 180000)
				time.Sleep(10 * time.Second)
			}
			for _, c := range conns {
				c.Close()
			}
		}()
		fmt.Fprintln(w, `{"status":"started"}`)
	})
	mux.HandleFunc("/healthz", func(w http.ResponseWriter, _ *http.Request) { fmt.Fprintln(w, "ok") })
	mux.HandleFunc("/version", func(w http.ResponseWriter, _ *http.Request) { fmt.Fprintf(w, `{"service":"scheduler","sha":%q,"stub":true}`, version) })
	mux.Handle("/metrics", reg.Handler())
	log.Infof("scheduler-stub starting version=%s", version)
	if err := http.ListenAndServe(":8090", mux); err != nil {
		log.Errorf("listen: %v", err)
	}
}
