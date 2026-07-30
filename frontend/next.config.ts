const allowedDevOrigins = (
  process.env.ALLOWED_DEV_ORIGINS ?? "localhost"
)
  .split(",")
  .map((origin) => origin.trim())
  .filter(Boolean);

const nextConfig = {
  reactStrictMode: true,
  output: "standalone",
  allowedDevOrigins,
};

export default nextConfig;