"use client";

import {
  TrendingDown,
  Users,
  Mail,
  UtensilsCrossed,
  Settings,
} from "lucide-react";

export type View =
  | "trends"
  | "suppliers"
  | "outreach"
  | "menu";

const workflow: { id: View; icon: React.ReactNode; label: string }[] = [
  { id: "menu", icon: <UtensilsCrossed className="h-4 w-4" />, label: "Menu" },
  { id: "trends", icon: <TrendingDown className="h-4 w-4" />, label: "Trends" },
  { id: "suppliers", icon: <Users className="h-4 w-4" />, label: "Suppliers" },
  { id: "outreach", icon: <Mail className="h-4 w-4" />, label: "Reach Out" },
];


interface Props {
  active: View;
  onNavigate: (view: View) => void;
  onSystemView: () => void;
  systemView: boolean;
  disabledTabs?: Set<View>;
}

function NavButton({
  active,
  onClick,
  icon,
  label,
  disabled,
}: {
  active: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  label: string;
  disabled?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`group relative rounded-md p-2.5 transition-colors ${
        disabled
          ? "text-muted-foreground/30 cursor-not-allowed"
          : active
            ? "bg-primary/10 text-primary"
            : "text-muted-foreground hover:text-foreground hover:bg-muted/50"
      }`}
    >
      {icon}
      <span className="pointer-events-none absolute left-full ml-2 whitespace-nowrap rounded-md bg-foreground px-2 py-1 text-xs text-background opacity-0 transition-opacity group-hover:opacity-100">
        {label}
      </span>
    </button>
  );
}

export default function Sidebar({ active, onNavigate, onSystemView, systemView, disabledTabs }: Props) {
  return (
    <nav className="fixed left-0 top-0 z-20 hidden h-screen w-12 flex-col items-center gap-1 border-r bg-background pt-20 md:flex">
      {workflow.map((item) => (
        <NavButton
          key={item.id}
          active={active === item.id}
          onClick={() => onNavigate(item.id)}
          icon={item.icon}
          label={item.label}
          disabled={disabledTabs?.has(item.id)}
        />
      ))}

      <div className="mt-auto mb-6 flex flex-col items-center gap-1">
        {active === "trends" && (
          <NavButton
            active={systemView}
            onClick={onSystemView}
            icon={<Settings className="h-4 w-4" />}
            label="System View"
          />
        )}
      </div>
    </nav>
  );
}
