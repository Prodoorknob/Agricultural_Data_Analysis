import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  env: {
    AWS_REGION: process.env.AWS_REGION || 'us-east-2',
  },
  serverExternalPackages: ['@aws-sdk/client-athena'],
};

export default nextConfig;
