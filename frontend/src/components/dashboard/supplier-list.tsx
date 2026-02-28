"use client";

import { MapPin, Phone, Globe } from "lucide-react";
import type { Supplier } from "@/lib/api";

interface Props {
  suppliers: Supplier[];
  emailCount: number;
}

export default function SupplierList({ suppliers, emailCount }: Props) {
  const sorted = [...suppliers].sort(
    (a, b) => (a.distance_miles ?? Infinity) - (b.distance_miles ?? Infinity)
  );

  return (
    <div>
      <p className="mb-3 text-sm text-muted-foreground">
        {suppliers.length} supplier{suppliers.length !== 1 ? "s" : ""} found
        {suppliers.length > emailCount && (
          <span className="text-muted-foreground/70">
            {" "}({suppliers.length - emailCount} missing contact info)
          </span>
        )}
      </p>
      <div className="space-y-2">
        {sorted.map((s) => (
          <div
            key={s.id}
            className="flex items-start justify-between rounded-md bg-muted/50 px-3 py-2"
          >
            <div className="min-w-0">
              <p className="text-sm font-medium truncate">{s.name}</p>
              {s.address && (
                <p className="text-xs text-muted-foreground truncate">{s.address}</p>
              )}
              <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5 mt-0.5">
                {s.email && (
                  <span className="text-xs text-muted-foreground">{s.email}</span>
                )}
                {s.phone && (
                  <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
                    <Phone className="h-3 w-3" />
                    {s.phone}
                  </span>
                )}
                {s.website && (
                  <a
                    href={s.website}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
                  >
                    <Globe className="h-3 w-3" />
                    Website
                  </a>
                )}
                {s.contact_name && (
                  <span className="text-xs text-muted-foreground">
                    Contact: {s.contact_name}
                  </span>
                )}
              </div>
            </div>
            {s.distance_miles != null && (
              <span className="inline-flex items-center gap-1 text-xs text-muted-foreground whitespace-nowrap shrink-0 ml-2">
                <MapPin className="h-3 w-3" />
                {s.distance_miles} mi
              </span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
