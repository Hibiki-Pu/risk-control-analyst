/**
 * A deliberately small markdown renderer (~130 lines).
 *
 * It supports exactly what the report builder emits: ATX headings, GFM-style tables, unordered and
 * ordered lists, blockquotes, horizontal rules, paragraphs, and inline `**bold**` / `` `code` `` /
 * `*italic*`. A full markdown dependency (remark + plugins ≈ 100 KB) was rejected on purpose: the
 * input is produced by our own deterministic report builder, and every construct it can emit is
 * covered here. Unknown syntax degrades to literal text rather than disappearing.
 */

import type { ReactNode } from "react";
import { Fragment } from "react";

/** Inline formatting: code spans first so their content is never re-parsed as markdown. */
export function renderInline(text: string, keyPrefix = "i"): ReactNode[] {
  const nodes: ReactNode[] = [];
  const pattern = /(`[^`]+`|\*\*[^*]+\*\*|\*[^*\n]+\*)/g;
  let cursor = 0;
  let match: RegExpExecArray | null;
  let index = 0;

  while ((match = pattern.exec(text)) !== null) {
    if (match.index > cursor) nodes.push(text.slice(cursor, match.index));
    const token = match[0];
    const key = `${keyPrefix}-${index++}`;
    if (token.startsWith("`")) {
      nodes.push(
        <code className="code" key={key}>
          {token.slice(1, -1)}
        </code>,
      );
    } else if (token.startsWith("**")) {
      nodes.push(
        <strong key={key} className="font-semibold text-ink">
          {token.slice(2, -2)}
        </strong>,
      );
    } else {
      nodes.push(<em key={key}>{token.slice(1, -1)}</em>);
    }
    cursor = match.index + token.length;
  }
  if (cursor < text.length) nodes.push(text.slice(cursor));
  return nodes;
}

function splitRow(line: string): string[] {
  return line
    .trim()
    .replace(/^\|/, "")
    .replace(/\|$/, "")
    .split("|")
    .map((cell) => cell.trim());
}

function isDivider(line: string): boolean {
  return /^\|?[\s:-]*-[\s|:-]*\|?$/.test(line.trim()) && line.includes("-");
}

export interface MarkdownProps {
  source: string;
  className?: string;
}

export function Markdown({ source, className = "" }: MarkdownProps) {
  const lines = source.replace(/\r\n/g, "\n").split("\n");
  const blocks: ReactNode[] = [];
  let index = 0;
  let key = 0;

  const nextKey = () => `b${key++}`;

  while (index < lines.length) {
    const line = lines[index] ?? "";

    if (!line.trim()) {
      index += 1;
      continue;
    }

    // Table: a header row followed by a divider row.
    if (line.trim().startsWith("|") && isDivider(lines[index + 1] ?? "")) {
      const header = splitRow(line);
      const rows: string[][] = [];
      index += 2;
      while (index < lines.length && (lines[index] ?? "").trim().startsWith("|")) {
        rows.push(splitRow(lines[index] ?? ""));
        index += 1;
      }
      blocks.push(
        <div className="overflow-x-auto" key={nextKey()}>
          <table className="table my-3">
            <thead>
              <tr>
                {header.map((cell, cellIndex) => (
                  <th key={cellIndex}>{renderInline(cell, `th${cellIndex}`)}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, rowIndex) => (
                <tr key={rowIndex}>
                  {header.map((_, cellIndex) => (
                    <td key={cellIndex}>{renderInline(row[cellIndex] ?? "", `td${rowIndex}-${cellIndex}`)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>,
      );
      continue;
    }

    const heading = /^(#{1,6})\s+(.*)$/.exec(line);
    if (heading) {
      const level = (heading[1] ?? "#").length;
      const text = heading[2] ?? "";
      const classes =
        level === 1
          ? "mt-4 text-lg font-semibold text-ink"
          : level === 2
            ? "mt-4 text-base font-semibold text-ink"
            : "mt-3 text-sm font-semibold text-ink";
      blocks.push(
        <p className={classes} key={nextKey()}>
          {renderInline(text, `h${level}`)}
        </p>,
      );
      index += 1;
      continue;
    }

    if (/^\s*([-*_])\s*\1\s*\1/.test(line) || /^-{3,}$/.test(line.trim())) {
      blocks.push(<hr className="my-3 border-line" key={nextKey()} />);
      index += 1;
      continue;
    }

    // Lists (both bullet styles, with one level of nesting rendered flat).
    if (/^\s*([-*+]|\d+\.)\s+/.test(line)) {
      const ordered = /^\s*\d+\./.test(line);
      const items: string[] = [];
      while (index < lines.length && /^\s*([-*+]|\d+\.)\s+/.test(lines[index] ?? "")) {
        items.push((lines[index] ?? "").replace(/^\s*([-*+]|\d+\.)\s+/, ""));
        index += 1;
      }
      const ListTag = ordered ? "ol" : "ul";
      blocks.push(
        <ListTag
          className={`my-2 space-y-1 pl-5 text-sm ${ordered ? "list-decimal" : "list-disc"}`}
          key={nextKey()}
        >
          {items.map((item, itemIndex) => (
            <li key={itemIndex}>{renderInline(item, `li${itemIndex}`)}</li>
          ))}
        </ListTag>,
      );
      continue;
    }

    if (line.trim().startsWith(">")) {
      const quote: string[] = [];
      while (index < lines.length && (lines[index] ?? "").trim().startsWith(">")) {
        quote.push((lines[index] ?? "").replace(/^\s*>\s?/, ""));
        index += 1;
      }
      blocks.push(
        <blockquote className="my-2 border-l-2 border-accent/60 pl-3 text-sm text-muted" key={nextKey()}>
          {quote.map((item, itemIndex) => (
            <Fragment key={itemIndex}>
              {renderInline(item, `q${itemIndex}`)}
              {itemIndex < quote.length - 1 ? <br /> : null}
            </Fragment>
          ))}
        </blockquote>,
      );
      continue;
    }

    // Paragraph: consume until a blank line or the start of another block.
    const paragraph: string[] = [];
    while (
      index < lines.length &&
      (lines[index] ?? "").trim() &&
      !/^(#{1,6})\s+/.test(lines[index] ?? "") &&
      !(lines[index] ?? "").trim().startsWith("|") &&
      !(lines[index] ?? "").trim().startsWith(">") &&
      !/^\s*([-*+]|\d+\.)\s+/.test(lines[index] ?? "")
    ) {
      paragraph.push(lines[index] ?? "");
      index += 1;
    }
    blocks.push(
      <p className="my-2 text-sm leading-relaxed text-ink" key={nextKey()}>
        {renderInline(paragraph.join(" "), "p")}
      </p>,
    );
  }

  return (
    <div className={className} data-testid="markdown-body">
      {blocks}
    </div>
  );
}

export default Markdown;
