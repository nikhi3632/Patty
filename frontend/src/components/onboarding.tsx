"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { setOptions, importLibrary } from "@googlemaps/js-api-loader";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
import { Upload } from "lucide-react";
import { analyze } from "@/lib/api";

interface Props {
  onAnalyzeStart: (restaurantId: string) => void;
}

interface PlaceData {
  address: string;
  lat: number;
  lng: number;
  state: string;
  city: string;
}

export default function Onboarding({ onAnalyzeStart }: Props) {
  const [name, setName] = useState("");
  const [place, setPlace] = useState<PlaceData | null>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);

  const addressRef = useRef<HTMLInputElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const key = process.env.NEXT_PUBLIC_GOOGLE_PLACES_API_KEY;
    if (!key || !addressRef.current) return;

    const input = addressRef.current;
    setOptions({ key, libraries: ["places"] });
    importLibrary("places").then((places) => {
      const autocomplete = new places.Autocomplete(
        input,
        {
          types: ["address"],
          componentRestrictions: { country: "us" },
          fields: ["formatted_address", "geometry", "address_components"],
        }
      );

      autocomplete.addListener("place_changed", () => {
        const result = autocomplete.getPlace();
        if (!result.geometry?.location) return;

        const components = result.address_components ?? [];
        let state = "";
        let city = "";
        for (const c of components) {
          if (c.types.includes("administrative_area_level_1")) {
            state = c.short_name;
          }
          if (c.types.includes("locality")) {
            city = c.long_name;
          }
        }

        setPlace({
          address: result.formatted_address ?? "",
          lat: result.geometry.location.lat(),
          lng: result.geometry.location.lng(),
          state,
          city,
        });
      });
    });
  }, []);

  const handleFiles = useCallback((incoming: FileList | File[]) => {
    const valid = Array.from(incoming).filter(
      (f) => f.type.startsWith("image/") || f.type === "application/pdf"
    );
    if (valid.length > 0) setFiles((prev) => [...prev, ...valid]);
  }, []);

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragging(false);
    handleFiles(e.dataTransfer.files);
  }

  function removeFile(index: number) {
    setFiles((prev) => prev.filter((_, i) => i !== index));
  }

  async function handleSubmit() {
    if (!name.trim() || !place || files.length === 0) return;
    setLoading(true);
    setError(null);

    try {
      const form = new FormData();
      form.append("name", name.trim());
      form.append("address", place.address);
      form.append("lat", String(place.lat));
      form.append("lng", String(place.lng));
      form.append("state", place.state);
      for (const f of files) {
        form.append("files", f);
      }

      const result = await analyze(form);
      onAnalyzeStart(result.restaurant_id);
    } catch {
      setError("Something went wrong uploading your menu. Please try again.");
      setLoading(false);
    }
  }

  const ready = name.trim() && place && files.length > 0 && !loading;

  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <div className="w-full max-w-md space-y-8">
        <div className="text-center">
          <h1 className="text-3xl font-semibold tracking-tight">Patty</h1>
          <p className="mt-2 text-muted-foreground">
            Upload your menu. We&apos;ll find savings.
          </p>
        </div>

        <div className="space-y-4">
          <Input
            placeholder="Restaurant name"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />

          <Input
            ref={addressRef}
            placeholder="Address"
          />

          {place && (
            <p className="text-sm text-muted-foreground">
              {place.address}
            </p>
          )}

          <Card
            className={`cursor-pointer border-2 border-dashed transition-colors ${
              dragging
                ? "border-primary bg-primary/5"
                : "border-muted-foreground/25 hover:border-muted-foreground/50"
            }`}
            onDragOver={(e) => {
              e.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
          >
            <CardContent className="flex flex-col items-center gap-2 py-8">
              <Upload className="h-8 w-8 text-muted-foreground" />
              <p className="text-sm text-muted-foreground">
                Drop menu files here or click to browse
              </p>
              <p className="text-xs text-muted-foreground/60">
                PDF, PNG, JPG
              </p>
            </CardContent>
          </Card>

          <input
            ref={fileInputRef}
            type="file"
            className="hidden"
            multiple
            accept="image/*,application/pdf"
            onChange={(e) => {
              if (e.target.files) handleFiles(e.target.files);
            }}
          />

          {files.length > 0 && (
            <div className="space-y-1">
              {files.map((f, i) => (
                <div
                  key={`${f.name}-${i}`}
                  className="flex items-center justify-between rounded-md bg-muted px-3 py-2 text-sm"
                >
                  <span className="truncate">{f.name}</span>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      removeFile(i);
                    }}
                    className="ml-2 text-muted-foreground hover:text-foreground"
                  >
                    &times;
                  </button>
                </div>
              ))}
            </div>
          )}

          {error && (
            <div className="rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
              {error}
            </div>
          )}

          <Button
            className="w-full"
            size="lg"
            disabled={!ready}
            onClick={handleSubmit}
          >
            {loading ? "Uploading..." : "Analyze"}
          </Button>
        </div>
      </div>
    </div>
  );
}
