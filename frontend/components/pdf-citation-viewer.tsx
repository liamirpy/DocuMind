"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { CloseIcon, DownloadIcon } from "@/components/icons";
import { ApiError } from "@/lib/auth-api";
import type {
  Document,
  PdfBoundingBox,
  RagSource,
} from "@/lib/types";
import {
  downloadDocument,
  getDocumentArrayBuffer,
} from "@/lib/workspace-api";

type PdfCitationViewerProps = {
  source: RagSource;
  document?: Document;
  onClose: () => void;
};

type HighlightRect = {
  left: number;
  top: number;
  width: number;
  height: number;
};

type PdfViewportLike = {
  width: number;
  height: number;
  transform?: readonly number[];
};

type PdfRenderTaskLike = {
  promise: Promise<void>;
  cancel: () => void;
};

type PdfPageLike = {
  getViewport: (options: {
    scale: number;
  }) => PdfViewportLike;

  render: (options: {
    canvas: HTMLCanvasElement;
    viewport: PdfViewportLike;
  }) => PdfRenderTaskLike;
};

type PdfDocumentLike = {
  numPages: number;
  getPage: (
    pageNumber: number,
  ) => Promise<PdfPageLike>;
};

type PdfLoadingTaskLike = {
  promise: Promise<PdfDocumentLike>;
  destroy?: () => Promise<void> | void;
};

function isBoundingBox(
  value: RagSource["bbox"],
): value is PdfBoundingBox {
  return Boolean(
    value &&
      typeof value === "object" &&
      [value.l, value.b, value.r, value.t].every(
        Number.isFinite,
      ),
  );
}

function transformPdfPoint(
  viewport: PdfViewportLike,
  x: number,
  y: number,
): [number, number] {
  const matrix = viewport.transform;

  if (!matrix || matrix.length !== 6) {
    throw new Error(
      "PDF viewport transformation matrix is unavailable.",
    );
  }

  const [a, b, c, d, e, f] = matrix;

  return [
    a * x + c * y + e,
    b * x + d * y + f,
  ];
}

function convertPdfBoundingBox(
  viewport: PdfViewportLike,
  bbox: PdfBoundingBox,
): HighlightRect {
  const points = [
    transformPdfPoint(viewport, bbox.l, bbox.b),
    transformPdfPoint(viewport, bbox.l, bbox.t),
    transformPdfPoint(viewport, bbox.r, bbox.b),
    transformPdfPoint(viewport, bbox.r, bbox.t),
  ];

  const xValues = points.map(([x]) => x);
  const yValues = points.map(([, y]) => y);

  const left = Math.min(...xValues);
  const right = Math.max(...xValues);
  const top = Math.min(...yValues);
  const bottom = Math.max(...yValues);

  return {
    left,
    top,
    width: right - left,
    height: bottom - top,
  };
}

function isRenderCancellation(
  error: unknown,
): boolean {
  if (!(error instanceof Error)) {
    return false;
  }

  return (
    error.name === "RenderingCancelledException" ||
    error.name === "AbortException" ||
    /cancel|aborted/i.test(error.message)
  );
}

function describeError(error: unknown): string {
  if (error instanceof Error) {
    return error.message || error.name;
  }

  return String(error);
}

function looksLikePdf(data: ArrayBuffer): boolean {
  const bytes = new Uint8Array(
    data,
    0,
    Math.min(data.byteLength, 5),
  );

  return String.fromCharCode(...bytes) === "%PDF-";
}

export function PdfCitationViewer({
  source,
  document,
  onClose,
}: PdfCitationViewerProps) {
  const canvasRef =
    useRef<HTMLCanvasElement>(null);

  const highlightRef =
    useRef<HTMLDivElement>(null);

  const renderTaskRef =
    useRef<PdfRenderTaskLike | null>(null);

  const [pdf, setPdf] =
    useState<PdfDocumentLike | null>(null);

  const [pageNumber, setPageNumber] = useState(
    Math.max(1, source.pageStart ?? 1),
  );

  const [pageCount, setPageCount] = useState(0);
  const [zoom, setZoom] = useState(1.25);

  const [pageSize, setPageSize] = useState({
    width: 0,
    height: 0,
  });

  const [highlight, setHighlight] =
    useState<HighlightRect | null>(null);

  const [loading, setLoading] = useState(true);
  const [rendering, setRendering] =
    useState(false);
  const [error, setError] = useState("");

  const documentName =
    document?.original_filename ||
    source.filename ||
    source.title ||
    "Source PDF";

  const citedPage = Math.max(
    1,
    source.pageStart ?? 1,
  );

  const bbox = useMemo(
    () =>
      isBoundingBox(source.bbox)
        ? source.bbox
        : null,
    [source.bbox],
  );

  useEffect(() => {
    const previousOverflow =
      documentBodyOverflow();

    return () => {
      restoreDocumentBodyOverflow(
        previousOverflow,
      );
    };
  }, []);

  /*
   * Download and parse the PDF once for the selected source.
   */
  useEffect(() => {
    let active = true;
    let loadingTask: PdfLoadingTaskLike | null = null;
    let loadingTaskDestroyed = false;

    async function destroyLoadingTask(): Promise<void> {
      if (
        loadingTaskDestroyed ||
        !loadingTask ||
        typeof loadingTask.destroy !== "function"
      ) {
        return;
      }

      loadingTaskDestroyed = true;

      try {
        await loadingTask.destroy();
      } catch {
        // Cleanup can race with worker shutdown.
      }
    }

    setPdf(null);
    setPageCount(0);
    setPageSize({ width: 0, height: 0 });
    setHighlight(null);
    setLoading(true);
    setRendering(false);
    setError("");

    async function loadPdf(): Promise<void> {
      try {
        const data =
          await getDocumentArrayBuffer(
            source.documentId,
          );

        if (!looksLikePdf(data)) {
          throw new Error(
            "The download endpoint did not return a PDF file.",
          );
        }

        const pdfjs =
          await import("pdfjs-dist");

        pdfjs.GlobalWorkerOptions.workerSrc =
          "/pdf.worker.min.mjs";

        loadingTask = pdfjs.getDocument({
          data: new Uint8Array(data),
        }) as unknown as PdfLoadingTaskLike;

        const loadedPdf =
          await loadingTask.promise;

        if (!active) {
          await destroyLoadingTask();
          return;
        }

        setPdf(loadedPdf);
        setPageCount(loadedPdf.numPages);
        setPageNumber(
          Math.min(citedPage, loadedPdf.numPages),
        );
      } catch (requestError: unknown) {
        if (!active) {
          return;
        }

        console.error(
          "Could not load citation PDF:",
          requestError,
        );

        setError(
          requestError instanceof ApiError ||
            requestError instanceof Error
            ? requestError.message
            : "Could not open the source PDF.",
        );
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    }

    void loadPdf();

    return () => {
      active = false;

      renderTaskRef.current?.cancel();
      renderTaskRef.current = null;

      void destroyLoadingTask();
    };
  }, [citedPage, source.documentId]);

  /*
   * Render every request into a brand-new off-screen canvas.
   *
   * PDF.js temporarily owns the canvas supplied to render().
   * Reusing the visible canvas during React Strict Mode,
   * zooming, or rapid page navigation can cause overlapping
   * render operations. A fresh canvas for each task removes
   * that race. Once rendering completes, its bitmap is copied
   * into the visible canvas.
   */
  useEffect(() => {
    if (!pdf) {
      return;
    }

    // Capture the narrowed document for use inside the async function.
    // React state can change between renders, so TypeScript does not keep
    // the `pdf !== null` narrowing across the nested async boundary.
    const currentPdf = pdf;

    let active = true;
    let localRenderTask: PdfRenderTaskLike | null = null;

    setRendering(true);
    setHighlight(null);
    setError("");

    async function renderPage(): Promise<void> {
      try {
        const page =
          await currentPdf.getPage(pageNumber);

        if (!active) {
          return;
        }

        const cssViewport = page.getViewport({
          scale: zoom,
        });

        const outputScale = Math.max(
          1,
          Math.min(window.devicePixelRatio || 1, 2),
        );

        const renderViewport = page.getViewport({
          scale: zoom * outputScale,
        });

        const renderCanvas =
          window.document.createElement("canvas");

        renderCanvas.width = Math.max(
          1,
          Math.ceil(renderViewport.width),
        );

        renderCanvas.height = Math.max(
          1,
          Math.ceil(renderViewport.height),
        );

        localRenderTask = page.render({
          canvas: renderCanvas,
          viewport: renderViewport,
        });

        renderTaskRef.current = localRenderTask;

        await localRenderTask.promise;

        if (!active) {
          return;
        }

        const visibleCanvas = canvasRef.current;

        if (!visibleCanvas) {
          return;
        }

        visibleCanvas.width = renderCanvas.width;
        visibleCanvas.height = renderCanvas.height;
        visibleCanvas.style.width =
          `${cssViewport.width}px`;
        visibleCanvas.style.height =
          `${cssViewport.height}px`;

        const visibleContext =
          visibleCanvas.getContext("2d", {
            alpha: false,
          });

        if (!visibleContext) {
          throw new Error(
            "The browser could not create a 2D canvas context.",
          );
        }

        visibleContext.save();
        visibleContext.setTransform(1, 0, 0, 1, 0, 0);
        visibleContext.clearRect(
          0,
          0,
          visibleCanvas.width,
          visibleCanvas.height,
        );
        visibleContext.drawImage(renderCanvas, 0, 0);
        visibleContext.restore();

        setPageSize({
          width: cssViewport.width,
          height: cssViewport.height,
        });

        if (
          bbox &&
          pageNumber === citedPage
        ) {
          
          setHighlight(
            convertPdfBoundingBox(
              cssViewport,
              bbox,
            ),
          );

          window.setTimeout(() => {
            if (!active) {
              return;
            }

            highlightRef.current?.scrollIntoView({
              behavior: "smooth",
              block: "center",
              inline: "center",
            });
          }, 80);
        }
      } catch (renderError: unknown) {
        if (
          !active ||
          isRenderCancellation(renderError)
        ) {
          return;
        }

        console.error(
          "PDF page rendering failed:",
          renderError,
        );

        setError(
          `Could not render this PDF page: ${describeError(
            renderError,
          )}`,
        );
      } finally {
        if (active) {
          setRendering(false);
        }

        if (
          renderTaskRef.current === localRenderTask
        ) {
          renderTaskRef.current = null;
        }
      }
    }

    void renderPage();

    return () => {
      active = false;
      localRenderTask?.cancel();

      if (
        renderTaskRef.current === localRenderTask
      ) {
        renderTaskRef.current = null;
      }
    };
  }, [
    bbox,
    citedPage,
    pageNumber,
    pdf,
    zoom,
  ]);

  return (
    <div
      aria-label={`Source viewer for ${documentName}`}
      aria-modal="true"
      className="pdf-viewer-backdrop"
      onMouseDown={(event) => {
        if (
          event.target === event.currentTarget
        ) {
          onClose();
        }
      }}
      role="dialog"
    >
      <section className="pdf-viewer-shell">
        <header className="pdf-viewer-header">
          <div>
            <p className="eyebrow">
              Citation [{source.citationId}]
            </p>

            <h2>{documentName}</h2>

            <p>
              {source.section ||
                "Referenced passage"}

              {source.pageStart
                ? ` · Page ${source.pageStart}`
                : ""}
            </p>
          </div>

          <div className="pdf-viewer-header-actions">
            {document && (
              <button
                className="pdf-toolbar-button"
                onClick={() => {
                  void downloadDocument(document);
                }}
                type="button"
              >
                <DownloadIcon />
                Download
              </button>
            )}

            <button
              aria-label="Close source viewer"
              className="icon-button"
              onClick={onClose}
              type="button"
            >
              <CloseIcon />
            </button>
          </div>
        </header>

        <div className="pdf-toolbar">
          <button
            className="pdf-toolbar-button"
            disabled={pageNumber <= 1 || rendering}
            onClick={() => {
              setPageNumber((current) =>
                Math.max(1, current - 1),
              );
            }}
            type="button"
          >
            Previous
          </button>

          <span>
            Page {pageNumber} of {pageCount || "—"}
          </span>

          <button
            className="pdf-toolbar-button"
            disabled={
              rendering ||
              !pageCount ||
              pageNumber >= pageCount
            }
            onClick={() => {
              setPageNumber((current) =>
                Math.min(pageCount, current + 1),
              );
            }}
            type="button"
          >
            Next
          </button>

          <div className="pdf-toolbar-spacer" />

          <button
            className="pdf-toolbar-button"
            disabled={rendering || zoom <= 0.65}
            onClick={() => {
              setZoom((current) =>
                Math.max(0.65, current - 0.2),
              );
            }}
            type="button"
          >
            −
          </button>

          <span>{Math.round(zoom * 100)}%</span>

          <button
            className="pdf-toolbar-button"
            disabled={rendering || zoom >= 2.6}
            onClick={() => {
              setZoom((current) =>
                Math.min(2.6, current + 0.2),
              );
            }}
            type="button"
          >
            +
          </button>

          {pageNumber !== citedPage && (
            <button
              className="pdf-toolbar-button is-accent"
              disabled={rendering}
              onClick={() => {
                setPageNumber(citedPage);
              }}
              type="button"
            >
              Back to citation
            </button>
          )}
        </div>

        <div className="pdf-viewer-body">
          {loading && (
            <div className="pdf-viewer-state">
              <div className="spinner" />
              <span>Opening source document…</span>
            </div>
          )}

          {!loading && rendering && !error && (
            <div className="pdf-viewer-state">
              <div className="spinner" />
              <span>Rendering page…</span>
            </div>
          )}

          {error && (
            <div className="pdf-viewer-error">
              {error}
            </div>
          )}

          {!loading && !error && (
            <div className="pdf-page-scroll">
              <div
                className="pdf-page-layer"
                style={{
                  width: pageSize.width,
                  height: pageSize.height,
                }}
              >
                <canvas ref={canvasRef} />

                {highlight && (
                  <div
                    aria-label="Cited passage highlight"
                    className="pdf-citation-highlight"
                    ref={highlightRef}
                    style={highlight}
                  />
                )}
              </div>
            </div>
          )}
        </div>
      </section>
    </div>
  );
}

function documentBodyOverflow(): string {
  const previous =
    window.document.body.style.overflow;

  window.document.body.style.overflow =
    "hidden";

  return previous;
}

function restoreDocumentBodyOverflow(
  previous: string,
): void {
  window.document.body.style.overflow =
    previous;
}
