package poolswitch

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"path"
	"strings"
	"time"
)

const defaultTimeout = 30 * time.Second

// Client forwards requests to a PoolSwitch proxy.
type Client struct {
	baseURL    *url.URL
	httpClient *http.Client
	headers    http.Header
}

// Option configures a Client.
type Option func(*Client)

// RequestOption configures a request.
type RequestOption func(*requestConfig)

type requestConfig struct {
	headers http.Header
}

// Response contains the raw HTTP response and body bytes.
type Response struct {
	StatusCode int
	Headers    http.Header
	Body       []byte
}

// Error is returned when the proxy responds with a non-success status code.
type Error struct {
	StatusCode int
	Body       string
}

func (e *Error) Error() string {
	return fmt.Sprintf("PoolSwitch proxy returned status %d: %s", e.StatusCode, e.Body)
}

// NewClient creates a proxy client using the provided base URL.
func NewClient(baseURL string, opts ...Option) *Client {
	parsed := mustParseBaseURL(baseURL)
	client := &Client{
		baseURL: parsed,
		httpClient: &http.Client{
			Timeout: defaultTimeout,
		},
		headers: make(http.Header),
	}
	for _, opt := range opts {
		opt(client)
	}
	return client
}

// WithHTTPClient overrides the underlying HTTP client.
func WithHTTPClient(httpClient *http.Client) Option {
	return func(c *Client) {
		if httpClient != nil {
			c.httpClient = httpClient
		}
	}
}

// WithTimeout configures the underlying client timeout.
func WithTimeout(timeout time.Duration) Option {
	return func(c *Client) {
		if timeout > 0 {
			c.httpClient.Timeout = timeout
		}
	}
}

// WithHeader adds a default header to every request.
func WithHeader(key, value string) Option {
	return func(c *Client) {
		c.headers.Set(key, value)
	}
}

// WithHeaders adds default headers to every request.
func WithHeaders(headers map[string]string) Option {
	return func(c *Client) {
		for key, value := range headers {
			c.headers.Set(key, value)
		}
	}
}

// WithRequestHeader adds a header to a single request.
func WithRequestHeader(key, value string) RequestOption {
	return func(cfg *requestConfig) {
		cfg.headers.Set(key, value)
	}
}

// WithRequestHeaders adds headers to a single request.
func WithRequestHeaders(headers map[string]string) RequestOption {
	return func(cfg *requestConfig) {
		for key, value := range headers {
			cfg.headers.Set(key, value)
		}
	}
}

// Request sends an arbitrary request and returns the raw response body.
func (c *Client) Request(ctx context.Context, method, endpoint string, body any, opts ...RequestOption) (*Response, error) {
	reqCfg := requestConfig{headers: cloneHeaders(c.headers)}
	for _, opt := range opts {
		opt(&reqCfg)
	}

	var reader io.Reader
	if body != nil {
		switch typed := body.(type) {
		case io.Reader:
			reader = typed
		case []byte:
			reader = bytes.NewReader(typed)
		case string:
			reader = strings.NewReader(typed)
		default:
			payload, err := json.Marshal(typed)
			if err != nil {
				return nil, fmt.Errorf("marshal request body: %w", err)
			}
			reader = bytes.NewReader(payload)
			if reqCfg.headers.Get("Content-Type") == "" {
				reqCfg.headers.Set("Content-Type", "application/json")
			}
		}
	}

	req, err := http.NewRequestWithContext(ctx, method, c.resolveURL(endpoint), reader)
	if err != nil {
		return nil, fmt.Errorf("create request: %w", err)
	}
	req.Header = reqCfg.headers

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("perform request: %w", err)
	}
	defer resp.Body.Close()

	bodyBytes, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("read response body: %w", err)
	}

	result := &Response{
		StatusCode: resp.StatusCode,
		Headers:    resp.Header.Clone(),
		Body:       bodyBytes,
	}

	if resp.StatusCode < http.StatusOK || resp.StatusCode >= http.StatusMultipleChoices {
		return result, &Error{
			StatusCode: resp.StatusCode,
			Body:       strings.TrimSpace(string(bodyBytes)),
		}
	}

	return result, nil
}

// RequestJSON sends a request and decodes the response JSON into out when provided.
func (c *Client) RequestJSON(ctx context.Context, method, endpoint string, body any, out any, opts ...RequestOption) error {
	resp, err := c.Request(ctx, method, endpoint, body, opts...)
	if err != nil {
		return err
	}
	if out == nil || len(resp.Body) == 0 {
		return nil
	}
	if err := json.Unmarshal(resp.Body, out); err != nil {
		return fmt.Errorf("decode response body: %w", err)
	}
	return nil
}

// Get performs a GET request and returns the raw response.
func (c *Client) Get(ctx context.Context, endpoint string, opts ...RequestOption) (*Response, error) {
	return c.Request(ctx, http.MethodGet, endpoint, nil, opts...)
}

// GetJSON performs a GET request and decodes the JSON response into out.
func (c *Client) GetJSON(ctx context.Context, endpoint string, out any, opts ...RequestOption) error {
	return c.RequestJSON(ctx, http.MethodGet, endpoint, nil, out, opts...)
}

// Post performs a POST request and returns the raw response.
func (c *Client) Post(ctx context.Context, endpoint string, body any, opts ...RequestOption) (*Response, error) {
	return c.Request(ctx, http.MethodPost, endpoint, body, opts...)
}

// PostJSON performs a POST request and decodes the JSON response into out.
func (c *Client) PostJSON(ctx context.Context, endpoint string, body any, out any, opts ...RequestOption) error {
	return c.RequestJSON(ctx, http.MethodPost, endpoint, body, out, opts...)
}

func (c *Client) resolveURL(endpoint string) string {
	u := *c.baseURL
	cleanPath := strings.TrimPrefix(endpoint, "/")
	u.Path = path.Join(c.baseURL.Path, cleanPath)
	return u.String()
}

func mustParseBaseURL(raw string) *url.URL {
	if raw == "" {
		panic("PoolSwitch base URL is required")
	}
	parsed, err := url.Parse(raw)
	if err != nil {
		panic(fmt.Sprintf("invalid PoolSwitch base URL: %v", err))
	}
	if parsed.Scheme == "" || parsed.Host == "" {
		panic("PoolSwitch base URL must include scheme and host")
	}
	return parsed
}

func cloneHeaders(headers http.Header) http.Header {
	cloned := make(http.Header, len(headers))
	for key, values := range headers {
		next := make([]string, len(values))
		copy(next, values)
		cloned[key] = next
	}
	return cloned
}


