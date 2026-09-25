// Package obs provides structured JSON logging and a minimal Prometheus text-format registry (no external deps).
// Every service exports the same metric names so the recording rules in observability/prometheus stay generic.
package obs

import (
	"bufio"
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"runtime"
	"sort"
	"strconv"
	"strings"
	"sync"
	"time"
)

var buckets = []float64{0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10}

type hist struct {
	counts []float64
	sum    float64
	total  float64
}

type gauge struct {
	name   string
	labels string
	fn     func() float64
}

type Registry struct {
	mu       sync.Mutex
	counters map[string]float64
	hists    map[string]*hist
	gauges   []gauge
}

func New() *Registry {
	return &Registry{counters: map[string]float64{}, hists: map[string]*hist{}}
}

func key(name, labels string) string { return name + "\x00" + labels }

func (r *Registry) Inc(name, labels string, v float64) {
	r.mu.Lock()
	r.counters[key(name, labels)] += v
	r.mu.Unlock()
}

func (r *Registry) Observe(name, labels string, v float64) {
	r.mu.Lock()
	defer r.mu.Unlock()
	k := key(name, labels)
	h, ok := r.hists[k]
	if !ok {
		h = &hist{counts: make([]float64, len(buckets))}
		r.hists[k] = h
	}
	for i, b := range buckets {
		if v <= b {
			h.counts[i]++
		}
	}
	h.sum += v
	h.total++
}

func (r *Registry) GaugeFunc(name, labels string, fn func() float64) {
	r.mu.Lock()
	r.gauges = append(r.gauges, gauge{name, labels, fn})
	r.mu.Unlock()
}

func join(a, b string) string {
	if a == "" {
		return b
	}
	if b == "" {
		return a
	}
	return a + "," + b
}

func brace(l string) string {
	if l == "" {
		return ""
	}
	return "{" + l + "}"
}

// Handler serves /metrics in Prometheus text format.
func (r *Registry) Handler() http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		r.mu.Lock()
		keys := make([]string, 0, len(r.counters))
		for k := range r.counters {
			keys = append(keys, k)
		}
		sort.Strings(keys)
		bw := bufio.NewWriter(w)
		for _, k := range keys {
			p := strings.SplitN(k, "\x00", 2)
			fmt.Fprintf(bw, "%s%s %g\n", p[0], brace(p[1]), r.counters[k])
		}
		hk := make([]string, 0, len(r.hists))
		for k := range r.hists {
			hk = append(hk, k)
		}
		sort.Strings(hk)
		for _, k := range hk {
			p := strings.SplitN(k, "\x00", 2)
			h := r.hists[k]
			for i, b := range buckets {
				fmt.Fprintf(bw, "%s_bucket{%s} %g\n", p[0], join(p[1], "le=\""+strconv.FormatFloat(b, 'g', -1, 64)+"\""), h.counts[i])
			}
			fmt.Fprintf(bw, "%s_bucket{%s} %g\n", p[0], join(p[1], "le=\"+Inf\""), h.total)
			fmt.Fprintf(bw, "%s_sum%s %g\n%s_count%s %g\n", p[0], brace(p[1]), h.sum, p[0], brace(p[1]), h.total)
		}
		gs := append([]gauge(nil), r.gauges...)
		r.mu.Unlock()
		for _, g := range gs {
			fmt.Fprintf(bw, "%s%s %g\n", g.name, brace(g.labels), g.fn())
		}
		bw.Flush()
	})
}

// RegisterProcess adds memory, cpu, goroutine and start-time gauges.
func (r *Registry) RegisterProcess() {
	started := float64(time.Now().Unix())
	r.GaugeFunc("process_start_time_seconds", "", func() float64 { return started })
	r.GaugeFunc("process_resident_memory_bytes", "", func() float64 {
		var m runtime.MemStats
		runtime.ReadMemStats(&m)
		return float64(m.Sys)
	})
	r.GaugeFunc("process_cpu_seconds_total", "", cpuSeconds)
	r.GaugeFunc("go_goroutines", "", func() float64 { return float64(runtime.NumGoroutine()) })
}

func cpuSeconds() float64 {
	b, err := os.ReadFile("/proc/self/stat")
	if err != nil {
		return 0
	}
	s := string(b)
	i := strings.LastIndex(s, ")")
	if i < 0 {
		return 0
	}
	f := strings.Fields(s[i+2:])
	if len(f) < 13 {
		return 0
	}
	ut, _ := strconv.ParseFloat(f[11], 64)
	st, _ := strconv.ParseFloat(f[12], 64)
	return (ut + st) / 100.0
}

// ---- logging ---------------------------------------------------------------

type Logger struct {
	service string
	replica string
	level   func() string
	reg     *Registry
	mu      sync.Mutex
	bytes   float64
}

var order = map[string]int{"debug": 0, "info": 1, "warn": 2, "error": 3}

func NewLogger(service, replica string, level func() string, reg *Registry) *Logger {
	l := &Logger{service: service, replica: replica, level: level, reg: reg}
	// Simulated disk: log bytes written against a 200MB quota, so a log flood shows up as a filling disk.
	reg.GaugeFunc("disk_used_ratio", "", func() float64 {
		l.mu.Lock()
		defer l.mu.Unlock()
		v := 0.35 + l.bytes/200e6
		if v > 1 {
			return 1
		}
		return v
	})
	return l
}

func (l *Logger) Log(level, msg string) {
	if order[level] < order[l.level()] {
		return
	}
	line, _ := json.Marshal(map[string]string{
		"ts": time.Now().UTC().Format(time.RFC3339Nano), "level": level, "service": l.service, "replica": l.replica, "msg": msg,
	})
	fmt.Fprintln(os.Stdout, string(line))
	l.mu.Lock()
	l.bytes += float64(len(line) + 1)
	l.mu.Unlock()
	l.reg.Inc("log_lines_total", "", 1)
}

func (l *Logger) Debugf(f string, a ...interface{}) { l.Log("debug", fmt.Sprintf(f, a...)) }
func (l *Logger) Infof(f string, a ...interface{})  { l.Log("info", fmt.Sprintf(f, a...)) }
func (l *Logger) Warnf(f string, a ...interface{})  { l.Log("warn", fmt.Sprintf(f, a...)) }
func (l *Logger) Errorf(f string, a ...interface{}) { l.Log("error", fmt.Sprintf(f, a...)) }

// ---- http middleware ---------------------------------------------------------

type rec struct {
	http.ResponseWriter
	status int
}

func (r *rec) WriteHeader(code int) {
	r.status = code
	r.ResponseWriter.WriteHeader(code)
}

// Middleware counts requests/errors, records latency, and converts panics into logged 500s.
func Middleware(reg *Registry, log *Logger, path string, next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()
		rw := &rec{ResponseWriter: w, status: 200}
		defer func() {
			if p := recover(); p != nil {
				log.Errorf("panic: %v in handlers.(*Handler).%s", p, path)
				rw.WriteHeader(500)
			}
			labels := fmt.Sprintf("path=%q,status=%q", path, strconv.Itoa(rw.status))
			reg.Inc("http_requests_total", labels, 1)
			reg.Observe("http_request_duration_seconds", fmt.Sprintf("path=%q", path), time.Since(start).Seconds())
		}()
		next.ServeHTTP(rw, r)
	})
}
