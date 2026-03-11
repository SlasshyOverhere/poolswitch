package poolswitch

import (
	"bytes"
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

type roundTripperFunc func(*http.Request) (*http.Response, error)

func (rt roundTripperFunc) RoundTrip(req *http.Request) (*http.Response, error) {
	return rt(req)
}

type errReader struct{}

func (errReader) Read(_ []byte) (int, error) { return 0, errors.New("read failed") }
func (errReader) Close() error               { return nil }

func TestMustParseBaseURL(t *testing.T) {
	assertPanics(t, func() { mustParseBaseURL("") })
	assertPanics(t, func() { mustParseBaseURL(":") })
	assertPanics(t, func() { mustParseBaseURL("example.com") })
}

func TestNewClientOptions(t *testing.T) {
	custom := &http.Client{Timeout: 10 * time.Second}
	client := NewClient(
		"https://example.com/base",
		WithHTTPClient(custom),
		WithTimeout(2*time.Second),
		WithHeader("X-One", "1"),
		WithHeaders(map[string]string{"X-Two": "2"}),
	)

	if client.httpClient != custom {
		t.Fatalf("expected custom http client")
	}
	if client.httpClient.Timeout != 2*time.Second {
		t.Fatalf("expected timeout to be updated")
	}
	if client.headers.Get("X-One") != "1" || client.headers.Get("X-Two") != "2" {
		t.Fatalf("expected headers to be set")
	}
}

func TestCloneHeaders(t *testing.T) {
	headers := http.Header{"X-Test": []string{"1"}}
	cloned := cloneHeaders(headers)
	cloned.Set("X-Test", "2")
	if headers.Get("X-Test") != "1" {
		t.Fatalf("expected clone to be independent")
	}
}

func TestResolveURL(t *testing.T) {
	client := NewClient("https://example.com/base")
	resolved := client.resolveURL("/v1/demo")
	if !strings.HasSuffix(resolved, "/base/v1/demo") {
		t.Fatalf("unexpected resolved URL: %s", resolved)
	}
}

func TestRequestBodiesAndHeaders(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("Content-Type") == "" {
			w.Header().Set("X-Content", "none")
		} else {
			w.Header().Set("X-Content", r.Header.Get("Content-Type"))
		}
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte("ok"))
	}))
	defer server.Close()

	client := NewClient(server.URL, WithHeader("X-Default", "yes"))
	ctx := context.Background()

	_, err := client.Request(ctx, http.MethodPost, "/json", map[string]string{"hello": "world"})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	_, err = client.Request(ctx, http.MethodPost, "/bytes", []byte("data"), WithRequestHeader("X-One", "1"))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	_, err = client.Request(ctx, http.MethodPost, "/string", "payload")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	reader := bytes.NewBufferString("stream")
	_, err = client.Request(ctx, http.MethodPost, "/reader", reader)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
}

func TestRequestJSON(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"ok":true}`))
	}))
	defer server.Close()

	client := NewClient(server.URL)
	ctx := context.Background()

	var payload map[string]bool
	if err := client.RequestJSON(ctx, http.MethodGet, "/demo", nil, &payload); err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if payload["ok"] != true {
		t.Fatalf("expected ok=true")
	}

	if err := client.RequestJSON(ctx, http.MethodGet, "/demo", nil, nil); err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
}

func TestRequestJSONEmptyBody(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusNoContent)
	}))
	defer server.Close()

	client := NewClient(server.URL)
	ctx := context.Background()

	var payload map[string]any
	if err := client.RequestJSON(ctx, http.MethodGet, "/demo", nil, &payload); err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
}

func TestRequestErrorPaths(t *testing.T) {
	client := NewClient("https://example.com")
	ctx := context.Background()

	_, err := client.Request(ctx, "INVALID METHOD", "/demo", nil)
	if err == nil {
		t.Fatalf("expected request creation error")
	}

	badBody := make(chan int)
	_, err = client.Request(ctx, http.MethodPost, "/demo", badBody)
	if err == nil {
		t.Fatalf("expected marshal error")
	}

	client.httpClient = &http.Client{Transport: roundTripperFunc(func(_ *http.Request) (*http.Response, error) {
		return nil, errors.New("network")
	})}
	_, err = client.Request(ctx, http.MethodGet, "/demo", nil)
	if err == nil {
		t.Fatalf("expected network error")
	}

	client.httpClient = &http.Client{Transport: roundTripperFunc(func(_ *http.Request) (*http.Response, error) {
		return &http.Response{StatusCode: http.StatusOK, Body: errReader{}}, nil
	})}
	_, err = client.Request(ctx, http.MethodGet, "/demo", nil)
	if err == nil {
		t.Fatalf("expected read error")
	}
}

func TestResponseErrors(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusBadRequest)
		_, _ = w.Write([]byte("bad"))
	}))
	defer server.Close()

	client := NewClient(server.URL)
	ctx := context.Background()

	resp, err := client.Request(ctx, http.MethodGet, "/demo", nil)
	if err == nil {
		t.Fatalf("expected error")
	}
	if resp.StatusCode != http.StatusBadRequest {
		t.Fatalf("expected 400")
	}
	if !strings.Contains(err.Error(), "PoolSwitch proxy returned status") {
		t.Fatalf("unexpected error string")
	}
}

func TestRequestJSONDecodeError(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte("not-json"))
	}))
	defer server.Close()

	client := NewClient(server.URL)
	ctx := context.Background()

	var payload map[string]any
	if err := client.RequestJSON(ctx, http.MethodGet, "/demo", nil, &payload); err == nil {
		t.Fatalf("expected decode error")
	}
}

func TestRequestJSONPropagatesError(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusBadRequest)
		_, _ = w.Write([]byte("bad"))
	}))
	defer server.Close()

	client := NewClient(server.URL)
	ctx := context.Background()

	var payload map[string]any
	if err := client.RequestJSON(ctx, http.MethodGet, "/demo", nil, &payload); err == nil {
		t.Fatalf("expected error")
	}
}

func TestHelpersAndRequestHeaders(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("X-Request") == "" {
			w.WriteHeader(http.StatusBadRequest)
			return
		}
		if r.Method == http.MethodPost {
			_, _ = w.Write([]byte(`{"ok":true}`))
			return
		}
		_, _ = w.Write([]byte(`{"ok":true}`))
	}))
	defer server.Close()

	client := NewClient(server.URL, WithHeaders(map[string]string{"X-Default": "yes"}))
	ctx := context.Background()

	_, err := client.Get(ctx, "/demo", WithRequestHeaders(map[string]string{"X-Request": "1"}))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	var payload map[string]bool
	if err := client.GetJSON(ctx, "/demo", &payload, WithRequestHeader("X-Request", "1")); err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if payload["ok"] != true {
		t.Fatalf("expected ok=true")
	}

	_, err = client.Post(ctx, "/demo", "body", WithRequestHeader("X-Request", "1"))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	payload = map[string]bool{}
	if err := client.PostJSON(ctx, "/demo", map[string]string{"hello": "world"}, &payload, WithRequestHeader("X-Request", "1")); err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if payload["ok"] != true {
		t.Fatalf("expected ok=true")
	}
}

func assertPanics(t *testing.T, fn func()) {
	t.Helper()
	defer func() {
		if recover() == nil {
			t.Fatalf("expected panic")
		}
	}()
	fn()
}


