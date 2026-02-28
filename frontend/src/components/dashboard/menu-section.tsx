"use client";

import { useEffect, useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { listMenuFiles, type Commodity, type MenuFile } from "@/lib/api";
import { titleCase } from "./commodity-data";
import Commodities from "./commodities";
import FilePreview from "./file-preview";

interface Props {
  restaurantId: string;
  commodities: Commodity[];
  pendingIds: Set<string>;
  onUpdate: () => void;
}

export default function MenuSection({ restaurantId, commodities, pendingIds, onUpdate }: Props) {
  const [menuFiles, setMenuFiles] = useState<MenuFile[]>([]);
  const [editing, setEditing] = useState(false);

  const tracked = commodities.filter((c) => c.status === "tracked");
  const active = tracked.filter((c) => !pendingIds.has(c.id));
  const awaiting = tracked.filter((c) => pendingIds.has(c.id));
  const other = commodities.filter((c) => c.status === "other");

  useEffect(() => {
    listMenuFiles(restaurantId).then((res) => {
      setMenuFiles(res.data);
    });
  }, [restaurantId]);

  return (
    <div className="space-y-3">
      {/* Menu file previews */}
      {menuFiles.length > 0 && (
        <div className="flex flex-wrap gap-3">
          {menuFiles.map((f) => (
            <FilePreview
              key={f.id}
              url={f.url}
              fileName={f.file_name}
              fileType={f.file_type}
            />
          ))}
        </div>
      )}

      {/* Tracked ingredient pills — split into active and awaiting */}
      {!editing && (
        <div className="space-y-4">
          {active.length > 0 && (
            <div className="space-y-2">
              <p className="text-sm text-muted-foreground">
                {active.length} active
              </p>
              <div className="flex flex-wrap gap-2">
                {active.map((c) => (
                  <span
                    key={c.id}
                    className="rounded-full border border-primary/30 bg-primary/10 px-3 py-1 text-xs font-medium text-primary"
                  >
                    {titleCase(c.commodities?.parent ?? c.raw_ingredient_name)}
                  </span>
                ))}
              </div>
            </div>
          )}

          {awaiting.length > 0 && (
            <div className="space-y-2">
              <p className="text-sm text-muted-foreground">
                {awaiting.length} awaiting data
              </p>
              <div className="flex flex-wrap gap-2">
                {awaiting.map((c) => (
                  <span
                    key={c.id}
                    className="rounded-full border border-dashed border-muted-foreground/40 px-3 py-1 text-xs font-medium text-muted-foreground"
                  >
                    {titleCase(c.commodities?.parent ?? c.raw_ingredient_name)}
                  </span>
                ))}
              </div>
            </div>
          )}

          {active.length === 0 && awaiting.length === 0 && (
            <p className="text-sm text-muted-foreground">No tracked ingredients</p>
          )}

          <Button
            variant="outline"
            size="sm"
            onClick={() => setEditing(true)}
          >
            Edit ingredients
          </Button>
        </div>
      )}

      {/* Edit mode — full review component */}
      {editing && (
        <div className="space-y-3">
          <Commodities
            restaurantId={restaurantId}
            commodities={commodities}
            onUpdate={onUpdate}
            mode="edit"
          />
          <Button
            variant="ghost"
            size="sm"
            className="text-muted-foreground"
            onClick={() => setEditing(false)}
          >
            Done editing
          </Button>
        </div>
      )}

      {/* Other ingredients summary */}
      {!editing && other.length > 0 && (
        <OtherSection other={other} />
      )}
    </div>
  );
}

function OtherSection({ other }: { other: Commodity[] }) {
  const [open, setOpen] = useState(false);
  const matchedNoData = other.filter((c) => c.commodity_id !== null);
  const unmatched = other.filter((c) => c.commodity_id === null);

  return (
    <div className="pt-2">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground"
      >
        {open ? (
          <ChevronDown className="h-4 w-4" />
        ) : (
          <ChevronRight className="h-4 w-4" />
        )}
        {other.length} other ingredient{other.length !== 1 ? "s" : ""}
      </button>
      {open && (
        <div className="mt-2 space-y-3">
          {matchedNoData.length > 0 && (
            <div className="space-y-1">
              <p className="text-xs text-muted-foreground">
                Matched, no pricing data for your market ({matchedNoData.length})
              </p>
              <div className="flex flex-wrap gap-2">
                {matchedNoData.map((c) => (
                  <span
                    key={c.id}
                    className="rounded-full bg-muted px-3 py-1 text-xs text-muted-foreground"
                  >
                    {titleCase(c.commodities?.parent ?? c.raw_ingredient_name)}
                  </span>
                ))}
              </div>
            </div>
          )}
          {unmatched.length > 0 && (
            <div className="space-y-1">
              <p className="text-xs text-muted-foreground">
                Not in our database ({unmatched.length})
              </p>
              <div className="flex flex-wrap gap-2">
                {unmatched.map((c) => (
                  <span
                    key={c.id}
                    className="rounded-full bg-muted px-3 py-1 text-xs text-muted-foreground"
                  >
                    {titleCase(c.raw_ingredient_name)}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
