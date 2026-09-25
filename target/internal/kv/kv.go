// Package kv is a tiny hot-reloading config store. Config lives in a git repo (target/config) that the chaos CLI and the
// runtime MCP server commit to; services poll the files so a config commit takes effect without a restart.
package kv

import (
	"bufio"
	"encoding/json"
	"fmt"
	"os"
	"strconv"
	"strings"
	"sync"
	"time"
)

type Store struct {
	mu     sync.RWMutex
	path   string
	vals   map[string]string
	isJSON bool
}

// New watches a flat "key: value" file (comments start with #).
func New(path string) *Store { return start(&Store{path: path, vals: map[string]string{}}) }

// NewJSON watches a flat JSON object (feature flags).
func NewJSON(path string) *Store { return start(&Store{path: path, vals: map[string]string{}, isJSON: true}) }

func start(s *Store) *Store {
	s.load()
	go func() {
		for {
			time.Sleep(time.Second)
			s.load()
		}
	}()
	return s
}

func (s *Store) load() {
	b, err := os.ReadFile(s.path)
	if err != nil {
		return
	}
	vals := map[string]string{}
	if s.isJSON {
		var m map[string]interface{}
		if json.Unmarshal(b, &m) != nil {
			return
		}
		for k, v := range m {
			vals[k] = fmt.Sprint(v)
		}
	} else {
		sc := bufio.NewScanner(strings.NewReader(string(b)))
		for sc.Scan() {
			line := strings.TrimSpace(sc.Text())
			if line == "" || strings.HasPrefix(line, "#") {
				continue
			}
			i := strings.Index(line, ":")
			if i < 0 {
				continue
			}
			vals[strings.TrimSpace(line[:i])] = strings.Trim(strings.TrimSpace(line[i+1:]), "\"")
		}
	}
	s.mu.Lock()
	s.vals = vals
	s.mu.Unlock()
}

func (s *Store) Str(key, def string) string {
	s.mu.RLock()
	defer s.mu.RUnlock()
	if v, ok := s.vals[key]; ok {
		return v
	}
	return def
}

func (s *Store) Int(key string, def int) int {
	n, err := strconv.Atoi(s.Str(key, ""))
	if err != nil {
		return def
	}
	return n
}

func (s *Store) Bool(key string, def bool) bool {
	b, err := strconv.ParseBool(s.Str(key, ""))
	if err != nil {
		return def
	}
	return b
}
