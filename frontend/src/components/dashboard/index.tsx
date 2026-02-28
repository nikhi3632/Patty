"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Loader2 } from "lucide-react";
import {
  getRestaurant,
  confirmRestaurant,
  listCommodities,
  listTrends,
  listSuppliers,
  listEmails,
  listCalibrations,
  subscribeToPipeline,
  refreshPrices,
  type Commodity,
  type Trend,
  type Supplier,
  type Email,
  type Calibration,
  type StreamEvent,
} from "@/lib/api";
import { buildCommodityViewModels, partitionViewModels } from "./commodity-data";
import Sidebar, { type View } from "./sidebar";
import Summary from "./summary";
import Commodities from "./commodities";
import CommodityCard from "./commodity-card";
import EmailSection from "./email-section";
import SupplierList from "./supplier-list";
import MenuSection from "./menu-section";

interface Props {
  restaurantId: string;
  onNewRestaurant?: () => void;
}

type StepStatus = "idle" | "running" | "done" | "error";

export default function Dashboard({ restaurantId, onNewRestaurant }: Props) {
  const [confirmed, setConfirmed] = useState<boolean | null>(null);
  const [commodities, setCommodities] = useState<Commodity[]>([]);
  const [trends, setTrends] = useState<Trend[]>([]);
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [emails, setEmails] = useState<Email[]>([]);
  const [calibrations, setCalibrations] = useState<Calibration[]>([]);
  const [systemView, setSystemView] = useState(false);
  const [loading, setLoading] = useState(true);
  const [activeView, setActiveView] = useState<View>("menu");
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());
  const didAutoExpand = useRef(false);

  // Pipeline stream 2 status per section
  const [pipelineStatus, setPipelineStatus] = useState({
    trends: "idle" as StepStatus,
    suppliers: "idle" as StepStatus,
    emails: "idle" as StepStatus,
  });
  const pipelineStarted = useRef(false);

  const load = useCallback(async () => {
    try {
      const [r, c, t, s, e] = await Promise.all([
        getRestaurant(restaurantId),
        listCommodities(restaurantId),
        listTrends(restaurantId),
        listSuppliers(restaurantId),
        listEmails(restaurantId),
      ]);
      setConfirmed(r.data.confirmed_at !== null);
      setCommodities(c.data);
      setTrends(t.data);
      setSuppliers(s.data);
      setEmails(e.data);
    } finally {
      setLoading(false);
    }
  }, [restaurantId]);

  useEffect(() => {
    load();
  }, [load]);

  // Start pipeline stream 2 when confirmed but data is missing
  const startPipeline = useCallback(() => {
    if (pipelineStarted.current) return;
    pipelineStarted.current = true;

    const cleanup = subscribeToPipeline(
      restaurantId,
      async (event: StreamEvent) => {
        if (event.step === "complete") return;
        const step = event.step as keyof typeof pipelineStatus;

        if (event.status === "running") {
          setPipelineStatus((prev) => ({ ...prev, [step]: "running" }));
        } else if (event.status === "done") {
          setPipelineStatus((prev) => ({ ...prev, [step]: "done" }));
          // Re-fetch the specific data that just completed
          if (step === "trends") {
            const t = await listTrends(restaurantId);
            setTrends(t.data);
          } else if (step === "suppliers") {
            const s = await listSuppliers(restaurantId);
            setSuppliers(s.data);
          } else if (step === "emails") {
            const e = await listEmails(restaurantId);
            setEmails(e.data);
          }
        } else if (event.status === "error") {
          setPipelineStatus((prev) => ({ ...prev, [step]: "error" }));
        }
      },
    );

    return cleanup;
  }, [restaurantId]);

  async function handleConfirm() {
    await confirmRestaurant(restaurantId);
    setConfirmed(true);
    startPipeline();
  }

  // On page load: if confirmed but no trend data, pipeline hasn't run yet
  useEffect(() => {
    if (confirmed && trends.length === 0 && suppliers.length === 0 && !pipelineStarted.current) {
      startPipeline();
    }
  }, [confirmed, trends.length, suppliers.length, startPipeline]);

  // Silent background refresh: fetch latest prices + recompute trends
  const refreshStarted = useRef(false);
  useEffect(() => {
    if (!confirmed || refreshStarted.current) return;
    refreshStarted.current = true;
    refreshPrices(restaurantId).then((res) => {
      if (res.status === "refreshing") {
        // Poll for updated trends after a delay (refresh takes ~30-60s)
        const timer = setTimeout(async () => {
          const t = await listTrends(restaurantId);
          setTrends(t.data);
        }, 45000);
        return () => clearTimeout(timer);
      }
    }).catch(() => {
      // Fire and forget — don't break the dashboard
    });
  }, [confirmed, restaurantId]);

  async function loadCalibrations() {
    const cal = await listCalibrations(restaurantId);
    setCalibrations(cal.data);
  }

  function toggleSystemView() {
    const next = !systemView;
    setSystemView(next);
    if (next && calibrations.length === 0) {
      loadCalibrations();
    }
  }

  const viewModels = buildCommodityViewModels(commodities, trends);
  const { actionable, stable, pending } = partitionViewModels(viewModels);
  const activeEmailCount = emails.filter((e) => e.status !== "sent" && e.status !== "discarded").length;
  const pendingIds = new Set(pending.map((vm) => vm.commodity.id));

  // Auto-expand first actionable card (once)
  const firstActionableId = actionable[0]?.commodity.id;
  if (!didAutoExpand.current && firstActionableId) {
    didAutoExpand.current = true;
    setExpandedIds(new Set([firstActionableId]));
  }

  const viewLabels: Record<View, string> = {
    trends: "Trends",
    suppliers: "Who's Nearby",
    outreach: "Reach Out",
    menu: "Menu & Ingredients",
  };

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <p className="text-muted-foreground">Loading dashboard...</p>
      </div>
    );
  }

  // Confirmation gate — show before dashboard unlocks
  if (!confirmed) {
    return (
      <div className="mx-auto max-w-xl px-4 py-12">
        <div className="mb-6">
          <h1 className="text-xl font-semibold tracking-tight">Patty</h1>
          <p className="text-sm text-muted-foreground">Smarter purchasing starts here</p>
          <p className="mt-2 text-sm text-muted-foreground">
            We scanned your menu and found these ingredients. Review and start tracking.
          </p>
        </div>
        <Commodities
          restaurantId={restaurantId}
          commodities={commodities}
          onUpdate={load}
          onConfirm={handleConfirm}
          mode="gate"
        />
      </div>
    );
  }

  // Helper: is a section still loading from the pipeline?
  const sectionLoading = (step: "trends" | "suppliers" | "emails") =>
    pipelineStatus[step] === "idle" || pipelineStatus[step] === "running";

  const pipelineRunning =
    sectionLoading("trends") && trends.length === 0;

  // Disable tabs whose data isn't ready yet
  const disabledTabs = new Set<View>();
  if (sectionLoading("suppliers") && suppliers.length === 0) disabledTabs.add("suppliers");
  if (sectionLoading("emails") && emails.length === 0) disabledTabs.add("outreach");
  if (sectionLoading("trends") && trends.length === 0) disabledTabs.add("trends");

  return (
    <>
      <Sidebar
        active={activeView}
        onNavigate={setActiveView}
        onSystemView={toggleSystemView}
        systemView={systemView}
        onNewRestaurant={onNewRestaurant}
        disabledTabs={disabledTabs}
      />

      <div className="mx-auto max-w-2xl px-4 py-8 md:pl-16">
        {/* Top bar */}
        <div className="mb-4 flex items-start justify-between">
          <div>
            <h1 className="text-xl font-semibold tracking-tight">Patty</h1>
            <p className="text-sm text-muted-foreground">Smarter purchasing starts here</p>
          </div>
          {onNewRestaurant && (
            <button
              onClick={onNewRestaurant}
              className="rounded-md border px-3 py-1.5 text-xs text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-colors"
            >
              + New Restaurant
            </button>
          )}
        </div>

        {/* Summary — always visible, count only items with trend data */}
        <Summary actionable={actionable} active={actionable.length + stable.length} pipelineRunning={pipelineRunning} />

        {/* View content */}
        <div className="mt-4 rounded-lg border p-5">
          <h2 className="mb-4 text-sm font-medium uppercase tracking-wider text-muted-foreground">
            {viewLabels[activeView]}
          </h2>

          {/* System view banner */}
          {activeView === "trends" && systemView && (
            <div className="mb-4 rounded-md border border-primary/30 bg-primary/5 px-3 py-2 text-xs text-primary">
              System view — showing calibration data and all signals
            </div>
          )}

          {/* USDA context note */}
          {activeView === "trends" && (actionable.length > 0 || stable.length > 0) && (
            <p className="mb-4 text-xs text-muted-foreground/70">
              Prices shown are USDA farm-gate (what farmers receive), not retail or wholesale. Trends reflect market direction.
            </p>
          )}

          {/* Trends — actionable + stable */}
          {activeView === "trends" && (
            <>
              {sectionLoading("trends") && trends.length === 0 ? (
                <SectionSpinner label="Computing trends..." />
              ) : pipelineStatus.trends === "error" && trends.length === 0 ? (
                <p className="text-sm text-destructive">
                  Could not compute trends. Try refreshing.
                </p>
              ) : (
                <div className="space-y-6">
                  {actionable.length > 0 && (
                    <div className="space-y-3">
                      {actionable.map((vm) => {
                        const cal = calibrations.find(
                          (c) => c.commodity_id === vm.commodity.commodity_id
                        );
                        return (
                          <CommodityCard
                            key={vm.commodity.id}
                            vm={vm}
                            expanded={expandedIds.has(vm.commodity.id)}
                            onToggle={() =>
                              setExpandedIds((prev) => {
                                const next = new Set(prev);
                                if (next.has(vm.commodity.id)) next.delete(vm.commodity.id);
                                else next.add(vm.commodity.id);
                                return next;
                              })
                            }
                            calibration={cal}
                            systemView={systemView}
                          />
                        );
                      })}
                    </div>
                  )}

                  {stable.length > 0 && (
                    <div className="space-y-3">
                      <h3 className="text-sm font-medium uppercase tracking-wider text-muted-foreground">
                        Within Normal Range
                      </h3>
                      {stable.map((vm) => {
                        const cal = calibrations.find(
                          (c) => c.commodity_id === vm.commodity.commodity_id
                        );
                        return (
                          <CommodityCard
                            key={vm.commodity.id}
                            vm={vm}
                            expanded={expandedIds.has(vm.commodity.id)}
                            onToggle={() =>
                              setExpandedIds((prev) => {
                                const next = new Set(prev);
                                if (next.has(vm.commodity.id)) next.delete(vm.commodity.id);
                                else next.add(vm.commodity.id);
                                return next;
                              })
                            }
                            calibration={cal}
                            systemView={systemView}
                          />
                        );
                      })}
                    </div>
                  )}

                  {actionable.length === 0 && stable.length === 0 && (
                    <p className="text-sm text-muted-foreground">
                      No trend data yet.
                    </p>
                  )}
                </div>
              )}
            </>
          )}

          {/* Suppliers — just the contact list */}
          {activeView === "suppliers" && (
            <>
              {sectionLoading("suppliers") && suppliers.length === 0 ? (
                <SectionSpinner label="Finding suppliers..." />
              ) : pipelineStatus.suppliers === "error" && suppliers.length === 0 ? (
                <p className="text-sm text-destructive">
                  Could not find suppliers. Try refreshing.
                </p>
              ) : suppliers.length > 0 ? (
                <SupplierList suppliers={suppliers} emailCount={activeEmailCount} />
              ) : (
                <p className="text-sm text-muted-foreground">No suppliers found yet.</p>
              )}
            </>
          )}

          {/* Outreach — just the email drafts */}
          {activeView === "outreach" && (
            <>
              {sectionLoading("emails") && emails.length === 0 ? (
                <SectionSpinner label="Drafting emails..." />
              ) : pipelineStatus.emails === "error" && emails.length === 0 ? (
                <p className="text-sm text-destructive">
                  Could not draft emails. Try refreshing.
                </p>
              ) : (
                <EmailSection emails={emails} onUpdate={load} />
              )}
            </>
          )}

          {/* Menu & Ingredients — menu preview + review component */}
          {activeView === "menu" && (
            <MenuSection
              restaurantId={restaurantId}
              commodities={commodities}
              pendingIds={pendingIds}
              onUpdate={load}
            />
          )}
        </div>
      </div>
    </>
  );
}

function SectionSpinner({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-3 py-8 justify-center">
      <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
      <p className="text-sm text-muted-foreground">{label}</p>
    </div>
  );
}
