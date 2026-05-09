// ESLint 9 flat config.
//
// Translation of the legacy `.eslintrc.cjs` (now removed). Behavior must
// match: same rule set, same ignore list, same `--max-warnings 0`
// strictness in `package.json`'s lint script. Verify with `bun run lint`
// before/after — output should be identical on the same files.

import js from "@eslint/js";
import tsParser from "@typescript-eslint/parser";
import tsPlugin from "@typescript-eslint/eslint-plugin";
import reactHooks from "eslint-plugin-react-hooks";
import globals from "globals";

export default [
  // Equivalent of `.eslintrc.cjs`'s `ignorePatterns`, plus the file-type
  // scope that the legacy `--ext .ts,.tsx` flag enforced. Flat config
  // doesn't read `--ext`; we get the same effect by ignoring everything
  // that isn't `.ts` / `.tsx`.
  {
    ignores: [
      "dist/**",
      "node_modules/**",
      "src/services/api/types.gen.ts",
      "**/*.cjs",
      "**/*.mjs",
      "**/*.js",
    ],
  },

  // Inherited recommended sets, in the same order as the eslintrc `extends`.
  js.configs.recommended,
  ...(tsPlugin.configs["flat/recommended"] ?? []),

  // Project-specific config for TS / TSX files.
  {
    files: ["**/*.ts", "**/*.tsx"],
    languageOptions: {
      parser: tsParser,
      parserOptions: {
        ecmaVersion: "latest",
        sourceType: "module",
        ecmaFeatures: { jsx: true },
      },
      // `env: { browser, es2022, node }` from the legacy config maps to
      // global declarations under flat config.
      globals: {
        ...globals.browser,
        ...globals.node,
        ...globals.es2022,
      },
    },
    plugins: {
      "@typescript-eslint": tsPlugin,
      "react-hooks": reactHooks,
    },
    rules: {
      "react-hooks/rules-of-hooks": "error",
      "react-hooks/exhaustive-deps": "warn",
      // `no-useless-assignment` was added to `eslint:recommended` after the
      // legacy eslintrc was last updated. Keep it off for the migration so
      // behavior matches the prior lint output. Enable it as a separate
      // commit if the team wants the new check.
      "no-useless-assignment": "off",
    },
    // The legacy eslintrc did not opt into unused-disable-directive
    // reporting; ESLint 9 flat config does by default. Mute it here so the
    // migration is purely a config translation.
    linterOptions: {
      reportUnusedDisableDirectives: "off",
    },
  },
];
