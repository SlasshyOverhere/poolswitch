import { defineConfig } from "vitepress";

function docsBase() {
  const repository = process.env.GITHUB_REPOSITORY?.split("/")[1];

  if (!process.env.GITHUB_ACTIONS || !repository) {
    return "/";
  }

  return repository.endsWith(".github.io") ? "/" : `/${repository}/`;
}

export default defineConfig({
  base: docsBase(),
  title: "PoolSwitch",
  description: "API key rotation, quota failover, retries, and cooldowns for embedded apps or proxy deployments.",
  lang: "en-US",
  cleanUrls: true,
  lastUpdated: true,
  head: [
    ["meta", { name: "theme-color", content: "#0d9373" }]
  ],
  themeConfig: {
    logo: "/logo.svg",
    siteTitle: "PoolSwitch Docs",
    search: {
      provider: "local"
    },
    nav: [
      { text: "Quickstart", link: "/quickstart" },
      { text: "Embedded Node", link: "/embedded-node" },
      { text: "Embedded Python", link: "/embedded-python" },
      { text: "Proxy Mode", link: "/proxy-mode" },
      { text: "GitHub", link: "https://github.com/SlasshyOverhere/poolswitch" }
    ],
    sidebar: [
      {
        text: "Getting Started",
        items: [
          { text: "Introduction", link: "/" },
          { text: "Quickstart", link: "/quickstart" }
        ]
      },
      {
        text: "Guides",
        items: [
          { text: "Embedded Node.js", link: "/embedded-node" },
          { text: "Embedded Python", link: "/embedded-python" },
          { text: "Proxy Mode", link: "/proxy-mode" },
          { text: "Configuration", link: "/configuration" },
          { text: "Strategies", link: "/strategies" }
        ]
      },
      {
        text: "Reference",
        items: [
          { text: "Architecture", link: "/architecture" },
          { text: "Metrics and Health", link: "/metrics-health" },
          { text: "Deployment", link: "/deployment" }
        ]
      }
    ],
    socialLinks: [
      { icon: "github", link: "https://github.com/SlasshyOverhere/poolswitch" }
    ],
    footer: {
      copyright: "Copyright 2026 PoolSwitch"
    }
  }
});
