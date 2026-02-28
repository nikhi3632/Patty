"use client";

import { useState } from "react";
import { X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  addCommodity,
  demoteCommodity,
  removeCommodity,
  type Commodity,
} from "@/lib/api";
import { titleCase } from "./commodity-data";

interface Props {
  restaurantId: string;
  commodities: Commodity[];
  onUpdate: () => void;
  onConfirm?: () => void;
  mode: "gate" | "edit";
}

export default function Commodities({
  restaurantId,
  commodities,
  onUpdate,
  onConfirm,
  mode,
}: Props) {
  const [newIngredient, setNewIngredient] = useState("");
  const [adding, setAdding] = useState(false);
  const [confirming, setConfirming] = useState(false);

  const tracked = commodities.filter((c) => c.status === "tracked");
  const matchedNoData = commodities.filter(
    (c) => c.status === "other" && c.commodity_id !== null
  );
  const unmatched = commodities.filter(
    (c) => c.status === "other" && c.commodity_id === null
  );

  async function handleDemote(id: string) {
    await demoteCommodity(id);
    onUpdate();
  }

  async function handleRemove(id: string) {
    await removeCommodity(id);
    onUpdate();
  }

  async function handleAdd() {
    if (!newIngredient.trim()) return;
    setAdding(true);
    try {
      await addCommodity(restaurantId, newIngredient.trim());
      setNewIngredient("");
      onUpdate();
    } finally {
      setAdding(false);
    }
  }

  async function handleConfirm() {
    setConfirming(true);
    try {
      onConfirm?.();
    } finally {
      setConfirming(false);
    }
  }

  return (
    <div className="space-y-6">
      {/* Tracked section */}
      <div className="space-y-2">
        <p className="text-sm font-medium">
          Tracked ({tracked.length})
        </p>
        <p className="text-xs text-muted-foreground">
          These ingredients get price alerts
        </p>
        {tracked.length > 0 ? (
          <div className="flex flex-wrap gap-2">
            {tracked.map((c) => (
              <Pill
                key={c.id}
                label={titleCase(c.commodities?.parent ?? c.raw_ingredient_name)}
                onRemove={() => handleDemote(c.id)}
                variant="tracked"
              />
            ))}
          </div>
        ) : (
          <p className="text-xs text-muted-foreground italic">
            No tracked ingredients yet
          </p>
        )}
      </div>

      {/* Matched but no data */}
      {matchedNoData.length > 0 && (
        <div className="space-y-2">
          <p className="text-sm font-medium">
            Matched, no pricing data yet ({matchedNoData.length})
          </p>
          <p className="text-xs text-muted-foreground">
            In our registry but no data for your market
          </p>
          <div className="flex flex-wrap gap-2">
            {matchedNoData.map((c) => (
              <Pill
                key={c.id}
                label={titleCase(c.commodities?.parent ?? c.raw_ingredient_name)}
                onRemove={() => handleRemove(c.id)}
                variant="muted"
              />
            ))}
          </div>
        </div>
      )}

      {/* Unmatched */}
      {unmatched.length > 0 && (
        <div className="space-y-2">
          <p className="text-sm font-medium">
            Not in our database ({unmatched.length})
          </p>
          <div className="flex flex-wrap gap-2">
            {unmatched.map((c) => (
              <Pill
                key={c.id}
                label={titleCase(c.raw_ingredient_name)}
                onRemove={() => handleRemove(c.id)}
                variant="muted"
              />
            ))}
          </div>
        </div>
      )}

      {/* Add ingredient */}
      <div className="flex gap-2">
        <Input
          placeholder="Add an ingredient..."
          value={newIngredient}
          onChange={(e) => setNewIngredient(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") handleAdd();
          }}
          className="flex-1"
        />
        <Button
          variant="outline"
          size="sm"
          disabled={!newIngredient.trim() || adding}
          onClick={handleAdd}
        >
          {adding ? "Adding..." : "Add"}
        </Button>
      </div>

      {/* Action button */}
      {mode === "gate" && (
        <Button
          className="w-full"
          disabled={tracked.length === 0 || confirming}
          onClick={handleConfirm}
        >
          {confirming ? "Starting..." : "Start tracking"}
        </Button>
      )}
    </div>
  );
}

function Pill({
  label,
  onRemove,
  variant,
}: {
  label: string;
  onRemove: () => void;
  variant: "tracked" | "muted";
}) {
  const colors =
    variant === "tracked"
      ? "bg-primary/10 text-primary"
      : "bg-muted text-muted-foreground";

  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-3 py-1 text-xs font-medium ${colors}`}
    >
      {label}
      <button
        onClick={onRemove}
        className="ml-0.5 rounded-full p-0.5 hover:bg-black/10"
      >
        <X className="h-3 w-3" />
      </button>
    </span>
  );
}
