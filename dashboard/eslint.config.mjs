// @ts-check
import nextPlugin from "@next/eslint-plugin-next";

/** @type {import("eslint").Linter.Config[]} */
const config = [
  {
    plugins: {
      "@next/next": nextPlugin,
    },
    rules: {
      ...nextPlugin.configs.recommended.rules,
      ...nextPlugin.configs["core-web-vitals"].rules,
    },
  },
  {
    ignores: [".next/**", "node_modules/**"],
  },
];

export default config;
