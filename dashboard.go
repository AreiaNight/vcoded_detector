package main

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log"
	"net/http"
	"net/url"
	"os/exec"
	"strings"
	"time"
)

// Upper limit for a whole scan, including downloading the page.
const crawlTimeout = 30 * time.Second

// Result is one signal found in the page.
type Result struct {
	Word  string `json:"word"`
	Count int    `json:"count"`
}

// Response is the JSON printed by crawler.py.
type Response struct {
	Status  int      `json:"status"`
	Source  string   `json:"source"`
	Total   int      `json:"total"`
	Results []Result `json:"results"`
}

func main() {
	mux := http.NewServeMux()
	mux.HandleFunc("GET /{$}", serveFile("Dashboard.html"))
	mux.HandleFunc("GET /styles.css", serveFile("styles.css"))
	mux.HandleFunc("GET /script.js", serveFile("script.js"))
	mux.HandleFunc("POST /api/analyze", analyzeAPI)

	fmt.Println("Open http://localhost:8080")
	log.Fatal(http.ListenAndServe("localhost:8080", mux))
}

// runCrawler runs the Python script and reads the JSON it prints to stdout.
// The scan stops if it hits crawlTimeout or the browser cancels the request.
func runCrawler(ctx context.Context, target string) (Response, error) {
	ctx, cancel := context.WithTimeout(ctx, crawlTimeout)
	defer cancel()

	var stderr bytes.Buffer
	cmd := exec.CommandContext(ctx, "python", "crawler.py", target)
	cmd.Stderr = &stderr

	output, err := cmd.Output()
	if errors.Is(ctx.Err(), context.DeadlineExceeded) {
		return Response{}, fmt.Errorf("scan timed out after %s", crawlTimeout)
	}
	if err != nil {
		if message := strings.TrimSpace(stderr.String()); message != "" {
			return Response{}, errors.New(message)
		}
		return Response{}, err
	}

	var data Response
	err = json.Unmarshal(output, &data)
	return data, err
}

// analyzeAPI gets the URL from the dashboard and replies with the scan results.
func analyzeAPI(w http.ResponseWriter, r *http.Request) {
	var request struct {
		URL string `json:"url"`
	}
	if err := json.NewDecoder(r.Body).Decode(&request); err != nil {
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

// serveFile serves one named file, so the rest of the folder stays private.
func serveFile(name string) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		http.ServeFile(w, r, name)
	}
}
