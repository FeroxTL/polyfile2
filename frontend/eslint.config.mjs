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
      "max-statements": "off",
      "no-console": "warn",
      "max-lines": "warn",
      "max-lines-per-function": "warn",
      "no-ternary": "off",
      "no-magic-numbers": ["warn", {
        "ignore": [-1, 0, 1, 2],
      }],
      "no-plusplus": "off",
      // TODO: enable
      "camelcase": "off",
      // TODO: enable
      "no-underscore-dangle": "off",
      "func-style": "off",
      "capitalized-comments": "warn",
      "no-unused-vars": "warn",
      "max-params": "off",
    }
  },
  {
    files: ["config/**/*.cjs"],
    languageOptions: {
      sourceType: "commonjs",
      globals: {
        ...globals.node,
      },
    },
    rules: {
      "prefer-named-capture-group": "off",
      "require-unicode-regexp": "off",
    },
  },
  { files: ["**/*.css"], plugins: { css }, language: "css/css" },
]);
