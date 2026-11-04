import type { NextConfig } from "next";

// Static export: the build is plain files for S3 + CloudFront (design doc, "AWS services map").
const config: NextConfig = {
  output: "export",
  // The repo's root AGENTS.md is the single source of instructions; don't let `next dev`
  // write a second one into web/.
  agentRules: false,
};

export default config;
