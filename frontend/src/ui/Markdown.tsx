import { Fragment, type ReactNode } from "react";

/**
 * A small, safe Markdown reader for director replies and long story text.
 *
 * It builds React elements (never HTML strings), so model output cannot inject
 * markup. Supported: paragraphs, hard line breaks, `#`–`###` headings, bullet
 * and numbered lists, `>` quotes, fenced code, `---` rules, **bold**, *italic*,
 * `code` and http(s) links. Anything else stays plain text.
 */

type Block =
  | { kind: "p"; lines: string[] }
  | { kind: "h"; level: 1 | 2 | 3; text: string }
  | { kind: "ul" | "ol"; items: string[]; start: number }
  | { kind: "quote"; lines: string[] }
  | { kind: "code"; text: string }
  | { kind: "hr" };

const BULLET = /^\s*[-*•]\s+(.*)$/;
const NUMBER = /^\s*(\d+)[.)]\s+(.*)$/;
const HEADING = /^(#{1,3})\s+(.*)$/;
const QUOTE = /^\s*>\s?(.*)$/;
const RULE = /^\s*(?:-{3,}|\*{3,}|_{3,})\s*$/;
const FENCE = /^\s*```/;

export function parseBlocks(source: string): Block[] {
  const lines = source.replace(/\r\n?/g, "\n").split("\n");
  const blocks: Block[] = [];
  let index = 0;
  while (index < lines.length) {
    const line = lines[index];
    if (!line.trim()) {
      index += 1;
      continue;
    }
    if (FENCE.test(line)) {
      const body: string[] = [];
      index += 1;
      while (index < lines.length && !FENCE.test(lines[index])) {
        body.push(lines[index]);
        index += 1;
      }
      index += 1;
      blocks.push({ kind: "code", text: body.join("\n") });
      continue;
    }
    if (RULE.test(line)) {
      blocks.push({ kind: "hr" });
      index += 1;
      continue;
    }
    const heading = HEADING.exec(line);
    if (heading) {
      blocks.push({
        kind: "h",
        level: heading[1].length as 1 | 2 | 3,
        text: heading[2].trim(),
      });
      index += 1;
      continue;
    }
    if (BULLET.test(line) || NUMBER.test(line)) {
      const ordered = !BULLET.test(line);
      const items: string[] = [];
      const start = ordered ? Number(NUMBER.exec(line)?.[1] || 1) : 1;
      while (index < lines.length) {
        const current = lines[index];
        const match = ordered ? NUMBER.exec(current) : BULLET.exec(current);
        if (match) {
          items.push(ordered ? match[2] : match[1]);
          index += 1;
          continue;
        }
        // An indented line continues the previous item.
        if (items.length && /^\s{2,}\S/.test(current)) {
          items[items.length - 1] += ` ${current.trim()}`;
          index += 1;
          continue;
        }
        break;
      }
      blocks.push({ kind: ordered ? "ol" : "ul", items, start });
      continue;
    }
    if (QUOTE.test(line)) {
      const quoted: string[] = [];
      while (index < lines.length && QUOTE.test(lines[index])) {
        quoted.push(QUOTE.exec(lines[index])?.[1] || "");
        index += 1;
      }
      blocks.push({ kind: "quote", lines: quoted });
      continue;
    }
    const paragraph: string[] = [];
    while (
      index < lines.length &&
      lines[index].trim() &&
      !FENCE.test(lines[index]) &&
      !HEADING.test(lines[index]) &&
      !BULLET.test(lines[index]) &&
      !NUMBER.test(lines[index]) &&
      !QUOTE.test(lines[index]) &&
      !RULE.test(lines[index])
    ) {
      paragraph.push(lines[index]);
      index += 1;
    }
    blocks.push({ kind: "p", lines: paragraph });
  }
  return blocks;
}

// Underscore emphasis is left out on purpose: shot ids and tool names
// (`get_brief`, `s01_intro`) would turn into italics.
const INLINE = /(`[^`\n]+`|\*\*[^*\n]+\*\*|\*[^*\s][^*\n]*\*|\[[^\]\n]+\]\(https?:\/\/[^)\s]+\))/g;

export function inline(text: string, keyPrefix = "i"): ReactNode[] {
  const parts = text.split(INLINE);
  return parts.map((part, index) => {
    const key = `${keyPrefix}-${index}`;
    if (!part) return null;
    if (part.startsWith("`") && part.endsWith("`") && part.length > 2) {
      return <code key={key}>{part.slice(1, -1)}</code>;
    }
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4) {
      return <strong key={key}>{part.slice(2, -2)}</strong>;
    }
    if (part.length > 2 && part.startsWith("*") && part.endsWith("*")) {
      return <em key={key}>{part.slice(1, -1)}</em>;
    }
    const link = /^\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)$/.exec(part);
    if (link) {
      return (
        <a key={key} href={link[2]} target="_blank" rel="noreferrer noopener">
          {link[1]}
        </a>
      );
    }
    return <Fragment key={key}>{part}</Fragment>;
  });
}

function lines(value: string[], key: string): ReactNode[] {
  return value.flatMap((line, index) =>
    index === 0
      ? inline(line, `${key}-${index}`)
      : [<br key={`${key}-br-${index}`} />, ...inline(line, `${key}-${index}`)],
  );
}

export function Markdown({ text, className = "" }: { text: string; className?: string }) {
  const blocks = parseBlocks(text || "");
  return (
    <div className={`md ${className}`}>
      {blocks.map((block, index) => {
        const key = `b${index}`;
        switch (block.kind) {
          case "h": {
            const Tag = (block.level === 1 ? "h3" : block.level === 2 ? "h4" : "h5") as
              | "h3"
              | "h4"
              | "h5";
            return <Tag key={key}>{inline(block.text, key)}</Tag>;
          }
          case "ul":
            return (
              <ul key={key}>
                {block.items.map((item, itemIndex) => (
                  <li key={`${key}-${itemIndex}`}>{inline(item, `${key}-${itemIndex}`)}</li>
                ))}
              </ul>
            );
          case "ol":
            return (
              <ol key={key} start={block.start}>
                {block.items.map((item, itemIndex) => (
                  <li key={`${key}-${itemIndex}`}>{inline(item, `${key}-${itemIndex}`)}</li>
                ))}
              </ol>
            );
          case "quote":
            return <blockquote key={key}>{lines(block.lines, key)}</blockquote>;
          case "code":
            return (
              <pre key={key}>
                <code>{block.text}</code>
              </pre>
            );
          case "hr":
            return <hr key={key} />;
          default:
            return <p key={key}>{lines(block.lines, key)}</p>;
        }
      })}
    </div>
  );
}
