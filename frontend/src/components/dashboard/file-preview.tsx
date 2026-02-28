"use client";

import { useEffect, useRef, useState } from "react";
import { FileText, ExternalLink } from "lucide-react";

interface Props {
  url: string;
  fileName: string;
  fileType: string;
}

export default function FilePreview({ url, fileName, fileType }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [loaded, setLoaded] = useState(false);
  const isPdf = fileType === "application/pdf";
  const isImage = fileType?.startsWith("image/");

  useEffect(() => {
    if (!isPdf || !canvasRef.current) return;

    let cancelled = false;

    async function renderPdf() {
      const pdfjsLib = await import("pdfjs-dist");
      pdfjsLib.GlobalWorkerOptions.workerSrc = new URL(
        "pdfjs-dist/build/pdf.worker.min.mjs",
        import.meta.url
      ).toString();

      const pdf = await pdfjsLib.getDocument(url).promise;
      const page = await pdf.getPage(1);

      if (cancelled || !canvasRef.current) return;

      const canvas = canvasRef.current;
      const ctx = canvas.getContext("2d");
      if (!ctx) return;

      // Render at 1.5x scale for crisp thumbnail
      const viewport = page.getViewport({ scale: 1.5 });
      canvas.width = viewport.width;
      canvas.height = viewport.height;

      await page.render({ canvasContext: ctx, viewport, canvas }).promise;
      if (!cancelled) setLoaded(true);
    }

    renderPdf().catch(() => {
      // Silently fail — fallback icon will show
    });

    return () => { cancelled = true; };
  }, [url, isPdf]);

  const displayName = fileName.length > 30
    ? fileName.slice(0, 27) + "..."
    : fileName;

  return (
    <a
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      className="group block w-48 overflow-hidden rounded-lg border transition-shadow hover:shadow-md"
    >
      {/* Preview area */}
      <div className="relative h-32 w-full overflow-hidden bg-muted">
        {isPdf && (
          <>
            <canvas
              ref={canvasRef}
              className={`h-full w-full object-cover object-top ${loaded ? "" : "hidden"}`}
            />
            {!loaded && (
              <div className="flex h-full w-full items-center justify-center">
                <FileText className="h-8 w-8 text-muted-foreground/50" />
              </div>
            )}
          </>
        )}
        {isImage && (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={url}
            alt={fileName}
            className="h-full w-full object-cover object-top"
          />
        )}
        {!isPdf && !isImage && (
          <div className="flex h-full w-full items-center justify-center">
            <FileText className="h-8 w-8 text-muted-foreground/50" />
          </div>
        )}
        {/* Hover overlay */}
        <div className="absolute inset-0 flex items-center justify-center bg-black/0 transition-colors group-hover:bg-black/10">
          <ExternalLink className="h-5 w-5 text-white opacity-0 transition-opacity group-hover:opacity-100 drop-shadow" />
        </div>
      </div>

      {/* File name */}
      <div className="flex items-center gap-2 px-3 py-2">
        <FileText className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
        <span className="truncate text-xs text-muted-foreground">{displayName}</span>
      </div>
    </a>
  );
}
