/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // react-pdf ships an ES-module PDF.js worker; the SWC minifier (default on
  // Next < 15) cannot minify it, so fall back to Terser here (react-pdf docs).
  swcMinify: false,
  webpack: (config) => {
    // pdfjs-dist's node build references the `canvas` package, which the
    // browser bundle never uses. Alias it out so the build resolves (react-pdf).
    config.resolve.alias.canvas = false;
    return config;
  },
};

export default nextConfig;