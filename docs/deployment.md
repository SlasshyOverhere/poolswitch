---
title: Deployment
description: Build the PoolSwitch docs into static files and deploy them to Netlify, Vercel, or any static host.
---

# Deployment

## Local development

Use Node.js 20 or 22 LTS.

```bash
npm install
npm run docs:dev
```

Open `http://127.0.0.1:3000`.

## Build static files

```bash
npm run docs:build
```

The generated static site is written to:

```text
docs/.vitepress/dist
```

That folder is what you can zip and deploy anywhere.

## Netlify

This repo already includes `netlify.toml`.

If you configure it manually, use:

- build command: `npm run docs:build`
- publish directory: `docs/.vitepress/dist`
- Node version: `22`

## Vercel

This repo already includes `vercel.json`.

If you configure it manually, use:

- install command: `npm install`
- build command: `npm run docs:build`
- output directory: `docs/.vitepress/dist`

## Direct zip deploy

If your host accepts static uploads:

1. run `npm run docs:build`
2. zip the contents of `docs/.vitepress/dist`
3. upload that zip to your host

## Recommended workflow

- keep docs in this repo
- update docs in pull requests
- preview locally with `npm run docs:dev`
- deploy from `main` or upload the built folder manually
