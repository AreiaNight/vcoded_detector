package main

import (
	"bufio"
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log"
	"net/http"
	"net/url"
	"os"
	"os/exec"
	"strconv"
	"strings"
	"time"
)

const crawlTimeout = 30 * time.Second
const databaseScanTimeout = 30 * time.Minute

type Result struct {
	Word  string `json:"word"`
	Count int    `json:"count"`
}
type Response struct {
	Status  int      `json:"status"`
	Source  string   `json:"source"`
	Total   int      `json:"total"`
	Results []Result `json:"results"`
}

func newMux() *http.ServeMux {
	mux := http.NewServeMux()
	mux.HandleFunc("GET /{$}", serveFile("Dashboard.html"))
	mux.HandleFunc("GET /styles.css", serveFile("styles.css"))
	mux.HandleFunc("GET /script.js", serveFile("script.js"))
	mux.HandleFunc("POST /api/analyze", analyzeAPI)
	mux.HandleFunc("GET /api/cashout-methods", cashoutMethodsAPI)
	mux.HandleFunc("POST /api/database-scan", databaseScanAPI)
	return mux
}
func main() {
	fmt.Println("Open http://localhost:8080")
	log.Fatal(http.ListenAndServe("localhost:8080", newMux()))
}
func pythonCommand(ctx context.Context, args ...string) *exec.Cmd {
	python := os.Getenv("PYTHON")
	if python == "" {
		python = "python"
	}
	return exec.CommandContext(ctx, python, args...)
}
func processError(ctx context.Context, stderr string, err error) error {
	if errors.Is(ctx.Err(), context.DeadlineExceeded) {
		return errors.New("scan timed out")
	}
	if message := strings.TrimSpace(stderr); message != "" {
		return errors.New(message)
	}
	return err
}
func runPython(ctx context.Context, args ...string) ([]byte, error) {
	var stderr bytes.Buffer
	cmd := pythonCommand(ctx, args...)
	cmd.Stderr = &stderr
	output, err := cmd.Output()
	if err != nil {
		return nil, processError(ctx, stderr.String(), err)
	}
	return output, nil
}
func runCrawler(ctx context.Context, target string) (Response, error) {
	ctx, cancel := context.WithTimeout(ctx, crawlTimeout)
	defer cancel()
	output, err := runPython(ctx, "crawler.py", target)
	if err != nil {
		return Response{}, err
	}
	var data Response
	err = json.Unmarshal(output, &data)
	return data, err
}
func analyzeAPI(w http.ResponseWriter, r *http.Request) {
	var request struct {
		URL string `json:"url"`
	}
	if err := json.NewDecoder(http.MaxBytesReader(w, r.Body, 8192)).Decode(&request); err != nil {
		http.Error(w, "Invalid JSON", http.StatusBadRequest)
		return
	}
	target := strings.TrimSpace(request.URL)
	parsed, err := url.Parse(target)
	if err != nil || (parsed.Scheme != "http" && parsed.Scheme != "https") || parsed.Host == "" {
		http.Error(w, "Enter a full http:// or https:// URL", http.StatusBadRequest)
		return
	}
	data, err := runCrawler(r.Context(), target)
	if err != nil {
		http.Error(w, "Analysis failed: "+err.Error(), http.StatusBadGateway)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(data)
}
func cashoutMethodsAPI(w http.ResponseWriter, r *http.Request) {
	ctx, cancel := context.WithTimeout(r.Context(), crawlTimeout)
	defer cancel()
	output, err := runPython(ctx, "database_scan.py", "--list-methods")
	if err != nil {
		http.Error(w, err.Error(), http.StatusBadGateway)
		return
	}
	if !json.Valid(output) {
		http.Error(w, "Invalid method list", http.StatusBadGateway)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Cache-Control", "no-store")
	w.Write(output)
}
func databaseScanAPI(w http.ResponseWriter, r *http.Request) {
	var request struct {
		MethodID *int `json:"cashout_method_id"`
		Limit    int  `json:"limit"`
	}
	if err := json.NewDecoder(http.MaxBytesReader(w, r.Body, 8192)).Decode(&request); err != nil {
		http.Error(w, "Invalid JSON", http.StatusBadRequest)
		return
	}
	if request.MethodID == nil || request.Limit < 1 || request.Limit > 1000 {
		http.Error(w, "Select a cashout method and a message limit between 1 and 1000", http.StatusBadRequest)
		return
	}
	ctx, cancel := context.WithTimeout(r.Context(), databaseScanTimeout)
	defer cancel()
	cmd := pythonCommand(ctx, "-u", "database_scan.py", "--cashout-method-id", strconv.Itoa(*request.MethodID), "--limit", strconv.Itoa(request.Limit))
	var stderr bytes.Buffer
	cmd.Stderr = &stderr
	stdout, err := cmd.StdoutPipe()
	if err != nil {
		http.Error(w, "Could not start scan", http.StatusBadGateway)
		return
	}
	if err = cmd.Start(); err != nil {
		http.Error(w, err.Error(), http.StatusBadGateway)
		return
	}
	scanner := bufio.NewScanner(stdout)
	scanner.Buffer(make([]byte, 4096), 4*1024*1024)
	started := false
	finished := false
	writeEvent := func(line []byte) bool {
		if _, err := w.Write(append(line, '\n')); err != nil {
			return false
		}
		if flusher, ok := w.(http.Flusher); ok {
			flusher.Flush()
		}
		return true
	}
	for scanner.Scan() {
		line := append([]byte(nil), scanner.Bytes()...)
		var event struct {
			Event string `json:"event"`
		}
		if json.Unmarshal(line, &event) != nil {
			cancel()
			break
		}
		if !started {
			w.Header().Set("Content-Type", "application/x-ndjson")
			w.Header().Set("Cache-Control", "no-store")
			w.Header().Set("X-Accel-Buffering", "no")
			started = true
		}
		if !writeEvent(line) {
			cancel()
			break
		}
		if event.Event == "completed" {
			finished = true
		}
	}
	if scanner.Err() != nil {
		cancel()
	}
	err = cmd.Wait()
	if !started {
		if err == nil {
			err = errors.New("scan returned no results")
		}
		http.Error(w, processError(ctx, stderr.String(), err).Error(), http.StatusBadGateway)
		return
	}
	if !finished {
		message := "Scan interrupted; results received so far are shown."
		if errors.Is(ctx.Err(), context.DeadlineExceeded) {
			message = "Scan reached the 30-minute limit; results received so far are shown."
		}
		event, _ := json.Marshal(map[string]string{"event": "error", "error": message})
		writeEvent(event)
	}
}
func serveFile(name string) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) { http.ServeFile(w, r, name) }
}
