import globals from "globals";
import js from "@eslint/js";
import css from "@eslint/css";
import { defineConfig } from "eslint/config";

export default defineConfig([
  {
    files: ["**/*.{js,mjs,cjs}"], languageOptions: {
      ecmaVersion: "latest",
      sourceType: "module",
      globals: globals.browser
    },
    rules: {
      ...js.configs.all.rules,
      "sort-imports": "off",
      "id-length": "off",
      "no-warning-comments": "off",
      "one-var": "off",
      "sort-keys": "off",
      "no-unused-expressions": "off",
      "max-statements": "off",
      "no-console": "warn",
      "max-lines": "warn",
      "max-lines-per-function": "warn",
      "no-ternary": "off",
      "no-magic-numbers": ["error", {
        "ignore": [-1, 0, 1],
      }],
    "no-plusplus": "off",
    // TODO: enable
    "camelcase": "off",
    // TODO: enable
    "no-underscore-dangle": "off",
    "func-style": "off",
    }
  },
  { files: ["**/*.css"], plugins: { css }, language: "css/css" },
]);
