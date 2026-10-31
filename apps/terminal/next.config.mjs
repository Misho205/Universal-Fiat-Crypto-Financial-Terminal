/** @type {import('next').NextConfig} */
const config = {
  reactStrictMode: true,
  // Static export for Modal hosting (all pages are client-side; API lives in Modal backend).
  output: "export",
  trailingSlash: true,
};
export default config;
