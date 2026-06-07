/**
 * Normalize LaTeX in AI/PDF-extracted exercise text so KaTeX can render it.
 *
 * Extraction output is inconsistent about math delimiters. We handle three cases:
 *  1. `\( … \)` / `\[ … \]` — the other standard TeX delimiters `remark-math`
 *     ignores — are rewritten to `$ … $` / `$$ … $$`.
 *  2. *Bare* LaTeX with no delimiters at all (the common breakage: `\frac{…}{…}`,
 *     `\lim_{x\to\infty}`, `e^{-x}`, `x^2`) is detected token-by-token and wrapped
 *     in `$ … $`, so the superscripts / fractions / operators actually render
 *     instead of showing as literal backslash noise.
 *  3. Text already inside `$ … $` / `$$ … $$` is left completely untouched.
 *
 * The bare-wrap is deliberately conservative to avoid mangling prose: superscripts
 * always wrap, but `_` only wraps with an explicit `{…}` group or a digit (so
 * `snake_case` words and `x_i`-style letter subscripts are left alone).
 */

// A LaTeX command (\frac, \lim, \log, \alpha…) plus any sub/superscripts and
// brace-argument groups that belong to it — matched as a single atom so
// `\frac{a}{b}` and `\lim_{x\to0}` wrap as one unit.
const COMMAND =
  "\\\\[a-zA-Z]+\\*?(?:\\s*[_^]\\s*(?:\\{[^{}]*\\}|[A-Za-z0-9]))*(?:\\s*\\{[^{}]*\\})*(?:\\s*[_^]\\s*(?:\\{[^{}]*\\}|[A-Za-z0-9]))*";

// A bare super/subscript on a base atom: `x^2`, `e^{-x}`, `a_{ij}`, `z_0`.
// Superscripts accept any single alnum or brace group; subscripts require a
// brace group or a digit (keeps prose underscores out).
const SCRIPT =
  "[A-Za-z0-9)\\]}](?:\\^\\s*(?:\\{[^{}]*\\}|[A-Za-z0-9])|_\\s*(?:\\{[^{}]*\\}|[0-9]))";

const ATOM = new RegExp(`${COMMAND}|${SCRIPT}`, "g");

/** Wrap each bare-LaTeX atom in a segment of plain (non-`$`) text. */
function wrapBareLatex(segment: string): string {
  return segment.replace(ATOM, (m) => `$${m.trim()}$`);
}

/**
 * Apply `fn` only to the parts of `text` that are NOT already inside `$…$` /
 * `$$…$$`, so existing math is never double-processed.
 */
function outsideMath(text: string, fn: (s: string) => string): string {
  // Capturing split → odd indices are the delimited math spans (left as-is).
  const parts = text.split(/(\$\$[\s\S]*?\$\$|\$[^$\n]*?\$)/g);
  return parts.map((part, i) => (i % 2 === 0 ? fn(part) : part)).join("");
}

export function normalizeLatex(src: string): string {
  if (!src) return src;
  const delimited = src
    .replace(/\\\[([\s\S]*?)\\\]/g, (_, inner) => `\n$$${inner.trim()}$$\n`)
    .replace(/\\\(([\s\S]*?)\\\)/g, (_, inner) => `$${inner.trim()}$`);
  return outsideMath(delimited, wrapBareLatex);
}
