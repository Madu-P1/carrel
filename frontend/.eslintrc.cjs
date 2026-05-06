module.exports = {
  root: true,
  env: {
    browser: true,
    es2022: true,
    node: true
  },
  parser: "@typescript-eslint/parser",
  parserOptions: {
    ecmaVersion: "latest",
    sourceType: "module",
    ecmaFeatures: {
      jsx: true
    }
  },
  plugins: ["@typescript-eslint", "react-hooks", "import", "jsx-a11y"],
  extends: [
    "eslint:recommended",
    "plugin:@typescript-eslint/recommended",
    "plugin:import/recommended",
    "plugin:import/typescript",
    "plugin:jsx-a11y/recommended"
  ],
  settings: {
    "import/resolver": {
      typescript: { project: "./tsconfig.json" },
      node: true
    }
  },
  ignorePatterns: ["dist", "node_modules", "src/services/api/types.gen.ts"],
  rules: {
    "react-hooks/rules-of-hooks": "error",
    "react-hooks/exhaustive-deps": "error",
    "@typescript-eslint/consistent-type-imports": [
      "error",
      { prefer: "type-imports", fixStyle: "inline-type-imports" }
    ],
    "import/order": [
      "error",
      {
        groups: ["builtin", "external", "internal", "parent", "sibling", "index"],
        pathGroups: [{ pattern: "@/**", group: "internal", position: "before" }],
        "newlines-between": "always",
        alphabetize: { order: "asc", caseInsensitive: true }
      }
    ],
    "import/no-duplicates": "error",
    // window.confirm / alert / prompt should never ship — use the
    // Dialog primitive instead. Caught the 2 surviving sites in
    // LibraryView.tsx and PlanView.tsx during the audit.
    "no-restricted-syntax": [
      "error",
      {
        selector:
          "CallExpression[callee.object.name='window'][callee.property.name=/^(confirm|alert|prompt)$/]",
        message:
          "Use the in-app Dialog primitive instead of window.confirm/alert/prompt."
      },
      {
        selector:
          "CallExpression[callee.name=/^(confirm|alert|prompt)$/]",
        message:
          "Use the in-app Dialog primitive instead of bare confirm/alert/prompt."
      }
    ]
  }
};
