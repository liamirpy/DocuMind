"use client";

import type { RagSource } from "@/lib/types";

type CitationAnswerProps = {
  content: string;
  sources?: RagSource[];
  onOpenSource: (source: RagSource) => void;
};

const CITATION_PATTERN = /\[(S\d+)\]/gi;

export function CitationAnswer({
  content,
  sources = [],
  onOpenSource,
}: CitationAnswerProps) {
  const sourceById = new Map(
    sources.map((source) => [source.citationId.toUpperCase(), source]),
  );

  const parts = content.split(CITATION_PATTERN);

  return (
    <div className="message-content">
      {parts.map((part, index) => {
        if (index % 2 === 0) {
          return <span key={`text-${index}`}>{part}</span>;
        }

        const citationId = part.toUpperCase();
        const source = sourceById.get(citationId);

        if (!source) {
          return <span key={`citation-${index}`}>[{part}]</span>;
        }

        const pageLabel = source.pageStart
          ? `page ${source.pageStart}${
              source.pageEnd && source.pageEnd !== source.pageStart
                ? `–${source.pageEnd}`
                : ""
            }`
          : "source";

        return (
          <button
            aria-label={`Open ${citationId}, ${pageLabel}`}
            className="citation-link"
            key={`citation-${index}`}
            onClick={() => onOpenSource(source)}
            title={`Open ${source.filename || source.title || "source document"}, ${pageLabel}`}
            type="button"
          >
            [{citationId}]
          </button>
        );
      })}
    </div>
  );
}
