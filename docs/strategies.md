---
title: Routing Strategies
description: Choose how your API traffic is distributed across keys.
---

# Routing Strategies

PoolSwitch supports multiple routing strategies to determine which API key should be used for a given request.

## `round_robin`

The simplest strategy. It evenly rotates requests across all available, healthy keys in order.

Best for:

- general load balancing when all keys have similar quotas and rate limits

## `least_used`

Selects the key that has processed the lowest total number of requests so far.

Best for:

- balancing overall load over a long period
- aggressively using a fresh key until its usage catches up

## `random`

Selects a random healthy key from the pool for each request.

Best for:

- very high concurrency environments
- avoiding overly deterministic routing patterns

## `quota_failover`

The most advanced strategy. It evaluates several factors to pick the best key:

1. estimated remaining quota
2. recent rate-limit behavior
3. error count
4. total requests

Best for:

- production environments with different quota tiers
- mixed free-tier and paid keys
- apps that want to maximize the usable budget before a key cools down

## Key states

Keys can move between a few important states:

- Healthy: ready to serve traffic
- Cooldown: temporarily disabled after quota exhaustion

By automatically applying cooldowns and choosing the next best key, PoolSwitch keeps requests flowing without manual intervention.
