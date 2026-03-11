# poolswitch-python

```python
from poolswitch_client import PoolSwitchClient

client = PoolSwitchClient("http://localhost:8080")
response = client.post("/v1/chat/completions", json={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "hello"}]})
print(response)
```


