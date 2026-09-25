// lb-stub: a stand-in for the C++ load balancer so the stack runs end to end today.
//
// It honours the SAME config keys and exports the SAME metric names as the real LB will, so swapping the real one in
// (same compose service name "lb") requires no change to alert rules, dashboards, chaos faults or the agents:
//
//	config/lb.yaml: upstream_timeout_ms, upstream_weight_orders_1, upstream_weight_orders_2, health_check_interval_ms
//	metrics: http_requests_total{path,status}, http_request_duration_seconds, upstream_healthy
package main

import (
	"context"
	"fmt"
	"math/rand"
	"net/http"
	"net/http/httputil"
	"net/url"
	"os"
	"strings"
	"sync"
	"time"

	"nightshift/target/internal/kv"
	"nightshift/target/internal/obs"
)

var version = "dev"

type upstream struct {
	name    string
	target  *url.URL
	proxy   *httputil.ReverseProxy
	healthy bool
	checked time.Time
}

func env(k, d string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return d
}

func main() {
	cfg := kv.New(env("CONFIG_FILE", "/config/lb.yaml"))
	reg := obs.New()
	reg.RegisterProcess()
	log := obs.NewLogger("lb", "lb-1", func() string { return cfg.Str("log_level", "info") }, reg)

	var mu sync.RWMutex
	var ups []*upstream
	for i, raw := range strings.Split(env("UPSTREAMS", "http://orders-svc-1:8080,http://orders-svc-2:8080"), ",") {
		u, err := url.Parse(strings.TrimSpace(raw))
		if err != nil {
			log.Errorf("bad upstream %q: %v", raw, err)
			os.Exit(1)
		}
		up := &upstream{name: fmt.Sprintf("orders-svc-%d", i+1), target: u, healthy: true, checked: time.Now()}
		up.proxy = httputil.NewSingleHostReverseProxy(u)
		up.proxy.ErrorHandler = func(w http.ResponseWriter, r *http.Request, err error) {
			if r.Context().Err() == context.DeadlineExceeded {
				log.Errorf("upstream timed out (%dms) while reading response from upstream %s path=%s", cfg.Int("upstream_timeout_ms", 2000), up.name, r.URL.Path)
				http.Error(w, "gateway timeout", http.StatusGatewayTimeout)
				return
			}
			log.Errorf("connect() failed (111: Connection refused) while connecting to upstream %s:8080", up.name)
			http.Error(w, "bad gateway", http.StatusBadGateway)
		}
		ups = append(ups, up)
	}
	reg.GaugeFunc("upstream_healthy", "", func() float64 {
		mu.RLock()
		defer mu.RUnlock()
		n := 0
		for _, u := range ups {
			if u.healthy {
				n++
			}
		}
		return float64(n)
	})

	go func() { // active health checks; a huge health_check_interval_ms means a dead replica keeps being routed to
		client := &http.Client{Timeout: time.Second}
		for {
			time.Sleep(time.Duration(cfg.Int("health_check_interval_ms", 2000)) * time.Millisecond)
			for _, u := range ups {
				resp, err := client.Get(u.target.String() + "/healthz")
				ok := err == nil && resp.StatusCode == 200
				if resp != nil {
					resp.Body.Close()
				}
				mu.Lock()
				u.healthy, u.checked = ok, time.Now()
				mu.Unlock()
			}
		}
	}()
	go func() {
		for {
			time.Sleep(30 * time.Second)
			mu.RLock()
			for _, u := range ups {
				if u.healthy {
					log.Warnf("upstream %s marked healthy (last check %dms ago)", u.name, time.Since(u.checked).Milliseconds())
				}
			}
			mu.RUnlock()
		}
	}()

	pick := func() *upstream {
		mu.RLock()
		defer mu.RUnlock()
		total := 0
		for i, u := range ups {
			if u.healthy {
				total += cfg.Int(fmt.Sprintf("upstream_weight_orders_%d", i+1), 50)
			}
		}
		if total <= 0 {
			return nil
		}
		n := rand.Intn(total)
		for i, u := range ups {
			if !u.healthy {
				continue
			}
			n -= cfg.Int(fmt.Sprintf("upstream_weight_orders_%d", i+1), 50)
			if n < 0 {
				return u
			}
		}
		return nil
	}

	proxy := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		u := pick()
		if u == nil {
			http.Error(w, "no healthy upstream", http.StatusServiceUnavailable)
			return
		}
		ctx, cancel := context.WithTimeout(r.Context(), time.Duration(cfg.Int("upstream_timeout_ms", 2000))*time.Millisecond)
		defer cancel()
		u.proxy.ServeHTTP(w, r.WithContext(ctx))
	})
	mux := http.NewServeMux()
	mux.Handle("/orders", obs.Middleware(reg, log, "/orders", proxy))
	mux.HandleFunc("/healthz", func(w http.ResponseWriter, _ *http.Request) { fmt.Fprintln(w, "ok") })
	mux.HandleFunc("/version", func(w http.ResponseWriter, _ *http.Request) { fmt.Fprintf(w, `{"service":"lb","sha":%q,"stub":true}`, version) })
	mux.Handle("/metrics", reg.Handler())
	log.Infof("lb-stub starting version=%s", version)
	if err := http.ListenAndServe(":8080", mux); err != nil {
		log.Errorf("listen: %v", err)
	}
}
