// Flat ESLint config: typescript-eslint recommended + React hooks rules over
// `src/`. Correctness-focused — formatting is left to the editor, and styling
// rules that would fight the existing codebase are not enabled.
import js from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import globals from "globals";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["dist", "node_modules"] },
  {
    files: ["src/**/*.{ts,tsx}"],
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    languageOptions: {
      ecmaVersion: 2022,
      globals: globals.browser,
    },
    plugins: {
      "react-hooks": reactHooks,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      // React-Compiler-era advisories (v6 preset). The codebase leans on the
      // "reset dialog state when it opens" effect pattern and canvas/ref work
      // these flag; adopting them means restructuring, not linting. Revisit if
      // the compiler is ever enabled.
      "react-hooks/set-state-in-effect": "off",
      "react-hooks/purity": "off",
      "react-hooks/refs": "off",
      "react-hooks/immutability": "off",
      // `catch {}` with a comment is used deliberately for best-effort paths.
      "no-empty": ["error", { allowEmptyCatch: true }],
      // Allow intentionally-unused args/vars with a leading underscore.
      "@typescript-eslint/no-unused-vars": [
        "error",
        { argsIgnorePattern: "^_", varsIgnorePattern: "^_" },
      ],
    },
  },
);
