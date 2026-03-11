---
layout: home

hero:
  name: PoolSwitch
  text: API key rotation without app-side failover code
  tagline: Rotate quota-limited API keys inside your app or behind a shared proxy.
  actions:
    - theme: brand
      text: Quickstart
      link: /quickstart
    - theme: alt
      text: GitHub
      link: https://github.com/SlasshyOverhere/poolswitch

features:
  - title: Embedded clients
    details: Use PoolSwitch directly inside Python, Node.js, or TypeScript apps.
  - title: Optional proxy mode
    details: Run the same engine as a local or shared HTTP gateway for any language.
  - title: Built for free-tier APIs
    details: Handle low monthly quotas, retries, cooldowns, and failover in one place.
  - title: Multiple strategies
    details: Choose round robin, least used, random, or quota failover.
  - title: Persistent state
    details: Keep key state in memory, Redis, or SQLite.
  - title: Production observability
    details: Expose health, status, and Prometheus-compatible metrics.
---

## Why PoolSwitch exists

Free-tier and quota-limited APIs are often too small for real applications.

If an API only gives you `100 searches per month`, one key is rarely enough. Most teams end up rebuilding the same plumbing over and over:

- rotate across several keys
- detect `429` or quota exhaustion
- put bad keys into cooldown
- retry safely with another account
- track which key is healthy right now

PoolSwitch packages that logic so developers can focus on their app instead of account juggling.

## Choose your mode

### Embedded package mode

Use the Python or Node.js client directly inside your app. This is the main product experience for most teams because there is no separate service to run.

### Proxy mode

Run a local or shared HTTP proxy when you want language-agnostic access from Go, curl, multiple services, or mixed-language teams.

## Start here

- [Quickstart](/quickstart)
- [Embedded Node.js Client](/embedded-node)
- [Embedded Python Client](/embedded-python)
- [Proxy Mode](/proxy-mode)
- [Deployment](/deployment)
