"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  Bell,
  MessageSquare,
  Bot,
  AlertTriangle,
  CheckCircle,
  Send,
  X,
} from "lucide-react";
import type { Notification } from "@/lib/api";
import {
  listNotifications,
  markNotificationRead,
  markAllNotificationsRead,
} from "@/lib/api";

const typeIcons: Record<string, React.ReactNode> = {
  inbound_reply: <MessageSquare className="h-3.5 w-3.5 text-blue-500" />,
  draft_ready: <Bot className="h-3.5 w-3.5 text-blue-500" />,
  auto_sent: <Send className="h-3.5 w-3.5 text-green-500" />,
  escalated: <AlertTriangle className="h-3.5 w-3.5 text-red-500" />,
  closed: <CheckCircle className="h-3.5 w-3.5 text-muted-foreground" />,
  reopened: <MessageSquare className="h-3.5 w-3.5 text-amber-500" />,
};

interface Props {
  restaurantId: string;
  onNavigateToThread?: (threadId: string) => void;
}

export default function NotificationBell({
  restaurantId,
  onNavigateToThread,
}: Props) {
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  const unreadCount = notifications.filter((n) => !n.read).length;

  const load = useCallback(async () => {
    try {
      const res = await listNotifications(restaurantId);
      setNotifications(res.data);
    } catch {
      // silent
    }
  }, [restaurantId]);

  // Poll for unread count every 30s (lightweight — just sets badge count)
  useEffect(() => {
    const poll = () => {
      listNotifications(restaurantId).then((res) => {
        setNotifications(res.data);
      }).catch(() => {});
    };
    const interval = setInterval(poll, 30000);
    return () => clearInterval(interval);
  }, [restaurantId]);

  // Close on click outside
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    if (open) document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [open]);

  async function handleClick(n: Notification) {
    if (!n.read) {
      await markNotificationRead(n.id);
      setNotifications((prev) =>
        prev.map((x) => (x.id === n.id ? { ...x, read: true } : x))
      );
    }
    if (n.thread_id && onNavigateToThread) {
      onNavigateToThread(n.thread_id);
      setOpen(false);
    }
  }

  async function handleMarkAllRead() {
    await markAllNotificationsRead(restaurantId);
    setNotifications((prev) => prev.map((n) => ({ ...n, read: true })));
  }

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => {
          setOpen(!open);
          if (!open) load();
        }}
        className="relative rounded-md p-1.5 text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-colors"
      >
        <Bell className="h-4 w-4" />
        {unreadCount > 0 && (
          <span className="absolute -top-0.5 -right-0.5 flex h-4 w-4 items-center justify-center rounded-full bg-red-500 text-[10px] font-medium text-white">
            {unreadCount > 9 ? "9+" : unreadCount}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 top-full mt-2 w-80 rounded-lg border bg-background shadow-lg z-50">
          <div className="flex items-center justify-between border-b px-3 py-2">
            <span className="text-xs font-medium">Notifications</span>
            <div className="flex items-center gap-2">
              {unreadCount > 0 && (
                <button
                  onClick={handleMarkAllRead}
                  className="text-[10px] text-muted-foreground hover:text-foreground"
                >
                  Mark all read
                </button>
              )}
              <button
                onClick={() => setOpen(false)}
                className="text-muted-foreground hover:text-foreground"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>

          <div className="max-h-80 overflow-y-auto">
            {notifications.length === 0 ? (
              <p className="px-3 py-6 text-center text-xs text-muted-foreground">
                No notifications yet
              </p>
            ) : (
              notifications.map((n) => (
                <button
                  key={n.id}
                  onClick={() => handleClick(n)}
                  className={`flex w-full items-start gap-2.5 px-3 py-2.5 text-left hover:bg-muted/30 transition-colors ${
                    !n.read ? "bg-blue-50/50" : ""
                  }`}
                >
                  <div className="shrink-0 mt-0.5">
                    {typeIcons[n.type] ?? (
                      <Bell className="h-3.5 w-3.5 text-muted-foreground" />
                    )}
                  </div>
                  <div className="min-w-0 flex-1">
                    <p
                      className={`text-xs ${!n.read ? "font-medium" : "text-muted-foreground"}`}
                    >
                      {n.title}
                    </p>
                    {n.body && (
                      <p className="truncate text-[10px] text-muted-foreground mt-0.5">
                        {n.body}
                      </p>
                    )}
                    <p className="text-[10px] text-muted-foreground/60 mt-0.5">
                      {formatRelative(n.created_at)}
                    </p>
                  </div>
                  {!n.read && (
                    <div className="shrink-0 mt-1.5">
                      <div className="h-2 w-2 rounded-full bg-blue-500" />
                    </div>
                  )}
                </button>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function formatRelative(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return `${days}d ago`;
}
