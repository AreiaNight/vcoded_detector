package main

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func fakePython(t *testing.T) {
	t.Helper()
	path := filepath.Join(t.TempDir(), "python")
	script := `#!/bin/sh
case "$*" in
  *--list-methods*) printf '%s\n' '[{"id":4,"method":"Wire transfer"}]' ;;
  *database_scan.py*)
    printf '%s\n' '{"event":"started","messages":1,"urls":1,"method":"Wire transfer"}'
    printf '%s\n' '{"event":"result","completed":1,"urls":1,"data":{"url":"https://example.com","status":200,"total":0,"results":[],"assessment":{"score":0,"level":"Low"}}}'
    printf '%s\n' '{"event":"completed","messages":1,"urls":1,"fetched":1,"failed":0}' ;;
  *) printf '%s\n' '{"status":200,"source":"view-source:https://example.com","total":0,"results":[],"assessment":{"score":0,"level":"Low"}}' ;;
esac
`
	if err := os.WriteFile(path, []byte(script), 0700); err != nil {
		t.Fatal(err)
	}
	t.Setenv("PYTHON", path)
}
func TestManualScanStillReturnsObject(t *testing.T) {
	fakePython(t)
	w := httptest.NewRecorder()
	newMux().ServeHTTP(w, httptest.NewRequest("POST", "/api/analyze", strings.NewReader(`{"url":"https://example.com"}`)))
	var data Response
	if w.Code != 200 || json.Unmarshal(w.Body.Bytes(), &data) != nil || data.Status != 200 || len(data.Assessment) == 0 {
		t.Fatalf("unexpected response: %d %s", w.Code, w.Body)
	}
}
func TestMethodNames(t *testing.T) {
	fakePython(t)
	w := httptest.NewRecorder()
	newMux().ServeHTTP(w, httptest.NewRequest("GET", "/api/cashout-methods", nil))
	if w.Code != 200 || !strings.Contains(w.Body.String(), "Wire transfer") {
		t.Fatalf("unexpected methods: %d %s", w.Code, w.Body)
	}
}
func TestDatabaseInputValidation(t *testing.T) {
	for _, body := range []string{`{}`, `{"cashout_method_id":4,"limit":0}`, `{"cashout_method_id":4,"limit":1001}`, `{"cashout_method_id":4,"limit":1.5}`, `{"cashout_method_id":"4","limit":15}`} {
		w := httptest.NewRecorder()
		newMux().ServeHTTP(w, httptest.NewRequest("POST", "/api/database-scan", strings.NewReader(body)))
		if w.Code != http.StatusBadRequest {
			t.Fatalf("expected validation error for %s, got %d", body, w.Code)
		}
	}
}
func TestDatabaseScanStreamsEvents(t *testing.T) {
	fakePython(t)
	w := httptest.NewRecorder()
	newMux().ServeHTTP(w, httptest.NewRequest("POST", "/api/database-scan", strings.NewReader(`{"cashout_method_id":4,"limit":15}`)))
	if w.Code != 200 || w.Header().Get("Content-Type") != "application/x-ndjson" {
		t.Fatalf("unexpected response: %d %s", w.Code, w.Body)
	}
	lines := strings.Split(strings.TrimSpace(w.Body.String()), "\n")
	if len(lines) != 3 {
		t.Fatalf("expected 3 events, got %s", w.Body)
	}
	for _, line := range lines {
		if !json.Valid([]byte(line)) {
			t.Fatal("invalid event", line)
		}
	}
	if !strings.Contains(lines[2], `"event":"completed"`) {
		t.Fatal("missing completion")
	}
}
func TestDatabaseFailureReturnsActionableError(t *testing.T) {
	path := filepath.Join(t.TempDir(), "python")
	if err := os.WriteFile(path, []byte("#!/bin/sh\necho 'Set COROBOMAIL_DSN before starting the dashboard.' >&2\nexit 1\n"), 0700); err != nil {
		t.Fatal(err)
	}
	t.Setenv("PYTHON", path)
	w := httptest.NewRecorder()
	newMux().ServeHTTP(w, httptest.NewRequest("POST", "/api/database-scan", strings.NewReader(`{"cashout_method_id":4,"limit":15}`)))
	if w.Code != 502 || !strings.Contains(w.Body.String(), "COROBOMAIL_DSN") {
		t.Fatalf("unexpected response: %d %s", w.Code, w.Body)
	}
}

func TestPDFRejectsInvalidReports(t *testing.T) {
	for _, body := range []string{`invalid`, `[]`, `{}`, `{"records":"not a list"}`} {
		w := httptest.NewRecorder()
		newMux().ServeHTTP(w, httptest.NewRequest("POST", "/api/export/pdf", strings.NewReader(body)))
		if w.Code != 400 {
			t.Fatalf("expected 400 for %s, got %d", body, w.Code)
		}
	}
}
func TestPDFDownloadHeaders(t *testing.T) {
	path := filepath.Join(t.TempDir(), "python")
	if err := os.WriteFile(path, []byte("#!/bin/sh\nprintf '%%PDF-1.4\\nexample'\n"), 0700); err != nil {
		t.Fatal(err)
	}
	t.Setenv("PYTHON", path)
	w := httptest.NewRecorder()
	newMux().ServeHTTP(w, httptest.NewRequest("POST", "/api/export/pdf", strings.NewReader(`{"records":[]}`)))
	if w.Code != 200 || w.Header().Get("Content-Type") != "application/pdf" || !strings.HasPrefix(w.Body.String(), "%PDF-") {
		t.Fatalf("unexpected PDF response: %d %s", w.Code, w.Body)
	}
}
