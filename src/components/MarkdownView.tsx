import ReactMarkdown from "react-markdown";
import rehypeKatex from "rehype-katex";
import rehypeRaw from "rehype-raw";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";

/**
 * Renders a note's markdown with native LaTeX and inline-HTML support.
 *
 * - `remark-math` + `rehype-katex` render `$inline$` and `$$block$$` math.
 * - `rehype-raw` keeps inline HTML (e.g. the `<span style="color">` and `<mark>`
 *   the editor emits for font color / highlight, which plain markdown can't
 *   express). Safe here: a local single-user app whose content is authored by
 *   the AI and the user themselves.
 */
export function MarkdownView({ children }: { children: string }) {
  return (
    <div className="prose prose-sm max-w-none dark:prose-invert">
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[rehypeRaw, rehypeKatex]}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
