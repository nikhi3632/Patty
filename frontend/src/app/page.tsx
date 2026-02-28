"use client";

import { useSyncExternalStore, useState } from "react";
import Onboarding from "@/components/onboarding";
import Processing from "@/components/processing";
import Dashboard from "@/components/dashboard/index";

const LS_KEY = "patty_restaurant_id";

function getStoredId(): string | null {
  return localStorage.getItem(LS_KEY);
}

function subscribe(cb: () => void) {
  window.addEventListener("storage", cb);
  return () => window.removeEventListener("storage", cb);
}

export default function Home() {
  const storedId = useSyncExternalStore(subscribe, getStoredId, () => null);
  const [processing, setProcessing] = useState(false);
  const [activeId, setActiveId] = useState<string | null>(null);

  const restaurantId = activeId ?? storedId;

  let view: "onboarding" | "processing" | "dashboard";
  if (processing && restaurantId) {
    view = "processing";
  } else if (restaurantId) {
    view = "dashboard";
  } else {
    view = "onboarding";
  }

  function handleAnalyzeStart(id: string) {
    setActiveId(id);
    localStorage.setItem(LS_KEY, id);
    setProcessing(true);
  }

  function handleProcessingComplete() {
    setProcessing(false);
  }

  return (
    <main className="min-h-screen bg-background">
      {view === "onboarding" && (
        <Onboarding onAnalyzeStart={handleAnalyzeStart} />
      )}
      {view === "processing" && restaurantId && (
        <Processing
          restaurantId={restaurantId}
          onComplete={handleProcessingComplete}
        />
      )}
      {view === "dashboard" && restaurantId && (
        <Dashboard restaurantId={restaurantId} />
      )}
    </main>
  );
}
