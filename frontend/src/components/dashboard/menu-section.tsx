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
  const withData = tracked.filter((c) => !pendingIds.has(c.id));
  const noData = tracked.filter((c) => pendingIds.has(c.id));
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

      {!editing && (
        <div className="space-y-4">
          {/* Tracked with data */}
          {withData.length > 0 && (
            <div className="space-y-2">
              <p className="text-sm text-muted-foreground">
                Tracked ({withData.length})
              </p>
              <div className="flex flex-wrap gap-2">
                {withData.map((c) => (
                  <span
                    key={c.id}
                    className="rounded-full border border-primary/30 bg-primary/10 px-3 py-1 text-xs font-medium text-primary"
                  >
                    {titleCase(c.commodities?.parent ?? c.raw_ingredient_name)}
                  </span>
                ))}
              </div>
              <p className="text-xs text-muted-foreground/70">
                Price data available — these show up in Trends.
              </p>
            </div>
          )}

          {/* Tracked, no data */}
          {noData.length > 0 && (
            <div className="space-y-2">
              <p className="text-sm text-muted-foreground">
                Tracked, no data ({noData.length})
              </p>
              <div className="flex flex-wrap gap-2">
                {noData.map((c) => (
                  <span
                    key={c.id}
                    className="rounded-full border border-dashed border-muted-foreground/40 px-3 py-1 text-xs font-medium text-muted-foreground"
                  >
                    {titleCase(c.commodities?.parent ?? c.raw_ingredient_name)}
                  </span>
                ))}
              </div>
              <p className="text-xs text-muted-foreground/70">
                No USDA pricing available for these commodities.
              </p>
            </div>
          )}

          {withData.length === 0 && noData.length === 0 && (
            <p className="text-sm text-muted-foreground">No tracked ingredients</p>
          )}

          <Button
            variant="outline"
            size="sm"
            onClick={() => setEditing(true)}
          >
            Edit ingredients
          </Button>

          {/* Other — flat list, no sub-groups */}
          {other.length > 0 && (
            <OtherSection other={other} />
          )}
        </div>
      )}

      {/* Edit mode */}
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
    </div>
  );
}

function OtherSection({ other }: { other: Commodity[] }) {
  const [open, setOpen] = useState(false);

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
        Other ({other.length})
      </button>
      {open && (
        <div className="mt-2 space-y-2">
          <div className="flex flex-wrap gap-2">
            {other.map((c) => (
              <span
                key={c.id}
                className="rounded-full bg-muted px-3 py-1 text-xs text-muted-foreground"
              >
                {titleCase(c.commodities?.parent ?? c.raw_ingredient_name)}
              </span>
            ))}
          </div>
          <p className="text-xs text-muted-foreground/70">
            Found on your menu but not tracked.
          </p>
        </div>
      )}
    </div>
  );
}
