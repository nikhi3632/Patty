"use client";

import { useEffect, useState } from "react";
import { subscribeToStream, type StreamEvent, type StreamEventResult } from "@/lib/api";
import { Check, Loader2, AlertCircle, FileText } from "lucide-react";

interface Props {
  restaurantId: string;
  onComplete: () => void;
}

type StepStatus = "pending" | "running" | "done" | "error";

function stepDetail(result?: StreamEventResult): string {
  if (!result) return "";
  if (result.skipped) return "Already parsed";
  return `Found ${result.tracked ?? 0} trackable commodities, ${result.other ?? 0} other ingredients`;
}

export default function Processing({ restaurantId, onComplete }: Props) {
  const [status, setStatus] = useState<StepStatus>("pending");
  const [detail, setDetail] = useState<string>("");

  useEffect(() => {
    const cleanup = subscribeToStream(
      restaurantId,
      (event: StreamEvent) => {
        if (event.step === "complete") {
          setTimeout(onComplete, 800);
          return;
        }

        if (event.step === "menu_parse") {
          if (event.status === "error") {
            setStatus("error");
            setDetail("Could not read your menu. Try uploading a clearer image.");
          } else if (event.status === "done") {
            setStatus("done");
            setDetail(stepDetail(event.result));
          } else {
            setStatus("running");
          }
        }
      },
      () => {
        setTimeout(onComplete, 1000);
      }
    );

    return cleanup;
  }, [restaurantId, onComplete]);

  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <div className="w-full max-w-sm space-y-8">
        <div className="text-center">
          <h1 className="text-2xl font-semibold tracking-tight">
            Reading your menu
          </h1>
          <p className="mt-2 text-sm text-muted-foreground">
            This takes a while
          </p>
        </div>

        <div className="flex flex-col items-center gap-4">
          <div
            className={`flex h-16 w-16 items-center justify-center rounded-full border-2 ${
              status === "done"
                ? "border-primary bg-primary text-primary-foreground"
                : status === "running"
                  ? "border-primary text-primary"
                  : status === "error"
                    ? "border-destructive text-destructive"
                    : "border-muted-foreground/25 text-muted-foreground/40"
            }`}
          >
            {status === "done" ? (
              <Check className="h-7 w-7" />
            ) : status === "running" ? (
              <Loader2 className="h-7 w-7 animate-spin" />
            ) : status === "error" ? (
              <AlertCircle className="h-7 w-7" />
            ) : (
              <FileText className="h-7 w-7" />
            )}
          </div>
          {detail && (
            <p className={`text-center text-sm ${status === "error" ? "text-destructive" : "text-muted-foreground"}`}>
              {detail}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
