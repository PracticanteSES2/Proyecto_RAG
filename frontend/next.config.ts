import type { NextConfig } from "next";

const config: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  devIndicators: false,
  // Sin AGENTS.md generado por `next dev` dentro de frontend/.
  agentRules: false,
};

export default config;
