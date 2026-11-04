import { Fragment, type ReactNode } from "react";

/**
 * Markdown-lite: paragraphs, "-"/"*" lists, **bold**, *italic*, `code`. Output is React elements
 * only (text nodes are escaped by React); no HTML, no links/images, nothing is ever injected raw.
 */
const INLINE = /(\*\*[^*\n]+\*\*|`[^`\n]+`|\*[^*\n]+\*)/g;

function inline(text: string): ReactNode[] {
  return text.split(INLINE).map((part, i) => {
    if (part.length > 4 && part.startsWith("**") && part.endsWith("**")) return <strong key={i}>{part.slice(2, -2)}</strong>;
    if (part.length > 2 && part.startsWith("`") && part.endsWith("`")) return <code key={i}>{part.slice(1, -1)}</code>;
    if (part.length > 2 && part.startsWith("*") && part.endsWith("*")) return <em key={i}>{part.slice(1, -1)}</em>;
    return <Fragment key={i}>{part}</Fragment>;
  });
}

export function Markdown({ text }: { text: string }) {
  const out: ReactNode[] = [];
  let list: string[] = [];
  let para: string[] = [];
  const flushList = () => {
    if (list.length > 0) {
      const items = list;
      out.push(
        <ul key={`u${out.length}`}>
          {items.map((l, i) => (
            <li key={i}>{inline(l)}</li>
          ))}
        </ul>,
      );
      list = [];
    }
  };
  const flushPara = () => {
    if (para.length > 0) {
      out.push(<p key={`p${out.length}`}>{inline(para.join(" "))}</p>);
      para = [];
    }
  };
  for (const raw of text.split(/\r?\n/)) {
    const m = /^\s*[-*]\s+(.*)$/.exec(raw);
    if (m !== null) {
      flushPara();
      list.push(m[1] ?? "");
    } else if (raw.trim() === "") {
      flushPara();
      flushList();
    } else {
      flushList();
      para.push(raw.trim());
    }
  }
  flushPara();
  flushList();
  return <>{out}</>;
}
