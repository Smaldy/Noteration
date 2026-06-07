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

// A bare super/subscript on a base atom: `x^2`, `e^-x`, `10^6`, `e^{2x}`, `z_0`.
// The base is a whole token — a number (`10`, `2.5`), an identifier (`x`, `mc`),
// or a closing bracket — so multi-char bases like `10^6` aren't split. The script
// body is a brace group, OR a signed run of alnum chars for `^` (so `e^-x`,
// `x^10`, `2^kt` all match), OR a brace/digit run for `_` (subscripts stay
// digit-only so prose `snake_case` / `x_i` aren't touched).
const BASE = "(?:\\d+(?:\\.\\d+)?|[A-Za-z][A-Za-z0-9]*|[)\\]}])";
const SUP = "\\^\\s*(?:\\{[^{}]*\\}|[+-]?[A-Za-z0-9]+)";
const SUB = "_\\s*(?:\\{[^{}]*\\}|[0-9]+)";
const SCRIPT = `${BASE}(?:${SUP}|${SUB})`;

const ATOM = new RegExp(`${COMMAND}|${SCRIPT}`, "g");

// Splits a bare script atom into base / operator / body.
const SCRIPT_PARTS = new RegExp(`^(${BASE})\\s*([_^])\\s*(.+)$`, "s");

/**
 * Brace a multi-character script body so KaTeX applies it whole: `x^10` → `x^{10}`,
 * `e^-x` → `e^{-x}`. A single-char or already-braced body is left as written
 * (`x^2`, `e^{2x}`). Used for bare super/subscript atoms only (not commands).
 */
function braceScript(atom: string): string {
  const m = SCRIPT_PARTS.exec(atom);
  if (!m) return atom;
  const [, base, op, rawBody] = m;
  const body = rawBody.trim();
  const braced = body.startsWith("{") ? body : `{${body}}`;
  return `${base}${op}${braced}`;
}

/** Wrap each bare-LaTeX atom in a segment of plain (non-`$`) text. */
function wrapBareLatex(segment: string): string {
  return segment.replace(ATOM, (m) => {
    // Command atoms (\frac{…}{…}, \lim_{…}) wrap verbatim; bare scripts get
    // their multi-char body braced so the whole exponent renders.
    const inner = m.trim().startsWith("\\") ? m.trim() : braceScript(m.trim());
    return `$${inner}$`;
  });
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
