/**
 * Turn AI/PDF-extracted exercise text into clean, well-structured Markdown + LaTeX
 * that KaTeX can render. Two layers:
 *
 *   normalizeLatex(src) — make the *math* render:
 *     1. `\( … \)` / `\[ … \]` → `$ … $` / `$$ … $$`.
 *     2. Bare LaTeX with no delimiters (`\frac{…}{…}`, `\lim_{…}`, `x^2`, `e^-x`),
 *        function notation (`f(x)`, `g(x,y)`), and primes (`y'`, `y''`, `f'(x)`)
 *        get wrapped in `$ … $`; multi-char exponents are braced (`x^10`→`x^{10}`).
 *     3. Adjacent math spans joined by a relation/operator are coalesced into one
 *        span so a whole equation (`g(x) = e^{-x}`) renders as a single formula.
 *     Text already inside `$ … $` / `$$ … $$` is never touched.
 *
 *   formatProblem(src) — also impose *structure* so a mashed-together blob reads
 *     well even when the model is sloppy: bold a leading "Problem N (…)" header,
 *     break each sub-question `(a) (b) …` onto its own line, promote a line that is
 *     purely one formula to centered display math, and pad display blocks with
 *     blank lines so remark-math treats them as centered blocks.
 *
 * The bare-wrap stays conservative so prose isn't mangled: subscripts only wrap
 * with a brace group or digits (prose `snake_case` / `x_i` untouched), function
 * calls require no space before `(` (so "see (above)" is left alone), and primes
 * must not be followed by a letter (so "don't" / "y's" are left alone).
 */

// \frac, \lim, \log, \alpha … plus the sub/superscripts and brace groups that
// belong to the command — matched as one atom.
const COMMAND =
  "\\\\[a-zA-Z]+\\*?(?:\\s*[_^]\\s*(?:\\{[^{}]*\\}|[A-Za-z0-9]))*(?:\\s*\\{[^{}]*\\})*(?:\\s*[_^]\\s*(?:\\{[^{}]*\\}|[A-Za-z0-9]))*";

// Function application: `f(x)`, `g(x,y)`, `sin(x)`. No space before `(` keeps
// prose parentheticals ("see (above)") out.
const FUNC = "[A-Za-z]\\w*\\([^()]*\\)";

// Primes / derivatives: `y'`, `y''`, `f'(x)`. The negative lookahead stops it
// from biting English apostrophes ("don't", "y's").
const PRIME = "[A-Za-z]'{1,3}(?![A-Za-z'])(?:\\([^()]*\\))?";

// A bare super/subscript on a whole base token (number, identifier, or bracket):
// `x^2`, `e^-x`, `10^6`, `e^{2x}`, `z_0`.
const BASE = "(?:\\d+(?:\\.\\d+)?|[A-Za-z][A-Za-z0-9]*|[)\\]}])";
const SUP = "\\^\\s*(?:\\{[^{}]*\\}|[+-]?[A-Za-z0-9]+)";
const SUB = "_\\s*(?:\\{[^{}]*\\}|[0-9]+)";
const SCRIPT = `${BASE}(?:${SUP}|${SUB})`;

// Order matters: command, then prime (so `f'(x)` beats `f(x)`), then func, script.
const ATOM = new RegExp(`${COMMAND}|${PRIME}|${FUNC}|${SCRIPT}`, "g");

/**
 * Brace a multi-character script body so KaTeX applies it whole: `x^10`→`x^{10}`,
 * `e^-x`→`e^{-x}`. Single-char or already-braced bodies stay as written. Applied
 * to the *inside* of any wrapped atom (handles scripts inside `f(x^10)` too).
 */
function braceScripts(expr: string): string {
  return expr.replace(
    /([_^])\s*(\{[^{}]*\}|[+-]?[A-Za-z0-9]+)/g,
    (_, op: string, body: string) => {
      if (body.startsWith("{")) return `${op}${body}`;
      return body.length > 1 || /^[+-]/.test(body) ? `${op}{${body}}` : `${op}${body}`;
    },
  );
}

/** Wrap each bare-LaTeX atom in a segment of plain (non-`$`) text. */
function wrapBareLatex(segment: string): string {
  return segment.replace(ATOM, (m) => {
    const t = m.trim();
    return t.startsWith("\\") ? `$${t}$` : `$${braceScripts(t)}$`;
  });
}

// Join `$a$ <op/space> $b$` (and directly-adjacent `$a$$b$` juxtaposition) into
// one span so a whole equation renders as a single formula.
const COALESCE =
  /\$([^$\n]+)\$(\s*[-+*/=<>≤≥≠≈±×÷·]\s*|\s+)\$([^$\n]+)\$/g;
const JUXT = /\$([^$\n]+)\$\$([^$\n]+)\$/g;

function coalesceOnce(text: string): string {
  let prev: string;
  let out = text;
  do {
    prev = out;
    out = out
      .replace(COALESCE, (_, a, glue, b) => `$${a}${glue}${b}$`)
      .replace(JUXT, (_, a, b) => `$${a} ${b}$`);
  } while (out !== prev);
  return out;
}

// Pull bare operator-joined operands that hang off an existing math span into it,
// so `$x^2$ + 1` → `$x^2 + 1$`. Anchored on a real span (which already proves it's
// math), so prose isn't swept in. Operands are numbers (incl. decimals),
// identifiers, or parenthesised groups — a trailing sentence period is NOT an
// operand, so it stays outside the math.
const OPERAND = "(?:\\([^()]*\\)|\\d+(?:\\.\\d+)?|[A-Za-z][A-Za-z0-9]*)";
const TRAIL = new RegExp(
  `\\$([^$\\n]+)\\$((?:[ \\t]*[-+*/=<>≤≥≠][ \\t]*${OPERAND})+)`,
  "g",
);
const LEAD = new RegExp(
  `((?:${OPERAND}[ \\t]*[-+*/=<>≤≥≠][ \\t]*)+)\\$([^$\\n]+)\\$`,
  "g",
);

/** Wrap + coalesce one plain (non-`$`) segment. */
function processSegment(segment: string): string {
  let out = coalesceOnce(wrapBareLatex(segment));
  out = out.replace(TRAIL, (_, a, trail) => `$${a}${trail}$`);
  out = out.replace(LEAD, (_, lead, b) => `$${lead}${b}$`);
  return coalesceOnce(out);
}

/**
 * Apply `processSegment` only to the parts of `text` NOT already inside `$…$` /
 * `$$…$$` — so pre-existing math (including `\[ \]`→`$$` display blocks) is never
 * re-processed, and the juxtaposition merge can't disturb a real `$$` delimiter.
 */
function outsideMath(text: string): string {
  const parts = text.split(/(\$\$[\s\S]*?\$\$|\$[^$\n]*?\$)/g);
  return parts.map((part, i) => (i % 2 === 0 ? processSegment(part) : part)).join("");
}

export function normalizeLatex(src: string): string {
  if (!src) return src;
  const delimited = src
    .replace(/\\\[([\s\S]*?)\\\]/g, (_, inner) => `\n$$${inner.trim()}$$\n`)
    .replace(/\\\(([\s\S]*?)\\\)/g, (_, inner) => `$${inner.trim()}$`);
  return outsideMath(delimited);
}

/** A line that is solely one inline formula → centered display math. */
function promoteDisplay(text: string): string {
  return text
    .split("\n")
    .map((line) => {
      const m = /^\s*\$([^$]+)\$\s*[.;,]?\s*$/.exec(line);
      return m ? `$$${m[1].trim()}$$` : line;
    })
    .join("\n");
}

/** Bold a leading "Problem 3 (6 points)" header onto its own line. */
function boldHeader(text: string): string {
  return text.replace(
    /^\s*((?:problem|exercise|question|part)\s+\d+\s*(?:\([^)]*\))?)\s*[:.\-—]?\s*/i,
    (_, head) => `**${head.trim()}**\n\n`,
  );
}

/** Force each sub-question `(a) (b) …` / `a) b) …` onto its own line. */
function splitSubparts(text: string): string {
  return text
    .replace(/(?<=\S)[ \t]+(?=\([a-hA-H]\)[ \t])/g, "\n\n")
    .replace(/(?<=\S)[ \t]+(?=[a-hA-H]\)[ \t])/g, "\n\n");
}

/** Pad display-math blocks with blank lines so they render as centered blocks. */
function padDisplay(text: string): string {
  return text
    .replace(/[ \t]*\$\$([\s\S]*?)\$\$[ \t]*/g, (_, m) => `\n\n$$${m.trim()}$$\n\n`)
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

/**
 * Full pipeline for an exercise/variant statement: render the math, then impose
 * readable structure.
 */
export function formatProblem(src: string): string {
  if (!src) return src;
  let out = normalizeLatex(src);
  out = promoteDisplay(out);
  out = boldHeader(out);
  out = splitSubparts(out);
  out = padDisplay(out);
  return out;
}
