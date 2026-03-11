# poolswitch-go

`poolswitch-go` is a lightweight Go client for a PoolSwitch proxy. It forwards HTTP requests to a locally running proxy and provides small conveniences for JSON payloads, headers, timeouts, and response decoding.

## Install

```bash
go get github.com/SlasshyOverhere/poolswitch/sdk-go
```

## Usage

```go
package main

import (
    "context"
    "fmt"
    "log"
    "time"

    poolswitch "github.com/SlasshyOverhere/poolswitch/sdk-go"
)

func main() {
    client := poolswitch.NewClient("http://localhost:8080", poolswitch.WithTimeout(30*time.Second))

    payload := map[string]any{
        "model": "gpt-4o-mini",
        "messages": []map[string]string{
            {"role": "user", "content": "Hello"},
        },
    }

    var response map[string]any
    if err := client.PostJSON(context.Background(), "/v1/chat/completions", payload, &response); err != nil {
        log.Fatal(err)
    }

    fmt.Println(response)
}
```

## Features

- Generic request API for any proxied endpoint
- Convenience methods for `GET`, `POST`, and JSON payloads
- Custom headers per request
- Configurable timeout
- Automatic JSON decoding into typed structs or `map[string]any`

## License

MIT

