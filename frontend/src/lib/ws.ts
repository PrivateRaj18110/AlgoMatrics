// Live-update channel: obtains a single-use ticket, connects to /api/v1/ws,
// subscribes to channels, and dispatches messages to listeners. Reconnects
// with backoff; consumers treat this as best-effort (REST remains truth).

import { api } from "@/lib/api";

type Listener = (message: Record<string, unknown>) => void;

interface TicketResponse {
  ticket: string;
}

export class LiveChannel {
  private socket: WebSocket | null = null;
  private listeners = new Map<string, Set<Listener>>();
  private channels = new Set<string>();
  private closed = false;
  private backoffMs = 1000;

  async connect(): Promise<void> {
    this.closed = false;
    await this.open();
  }

  private async open(): Promise<void> {
    if (this.closed) return;
    let ticket: string;
    try {
      const response = await api<TicketResponse>("/auth/ws-ticket", { method: "POST" });
      ticket = response.ticket;
    } catch {
      this.scheduleReconnect();
      return;
    }
    const protocol = window.location.protocol === "https:" ? "wss" : "ws";
    const url = `${protocol}://${window.location.host}/api/v1/ws?ticket=${encodeURIComponent(ticket)}`;
    const socket = new WebSocket(url);
    this.socket = socket;

    socket.onopen = () => {
      this.backoffMs = 1000;
      if (this.channels.size > 0) {
        socket.send(JSON.stringify({ action: "subscribe", channels: [...this.channels] }));
      }
    };
    socket.onmessage = (event) => {
      try {
        const message = JSON.parse(String(event.data)) as Record<string, unknown>;
        const channel = typeof message.channel === "string" ? message.channel : null;
        if (channel) {
          this.listeners.get(channel)?.forEach((listener) => listener(message));
        }
      } catch {
        // ignore malformed frames
      }
    };
    socket.onclose = () => {
      this.socket = null;
      this.scheduleReconnect();
    };
    socket.onerror = () => {
      socket.close();
    };
  }

  private scheduleReconnect(): void {
    if (this.closed) return;
    window.setTimeout(() => void this.open(), this.backoffMs);
    this.backoffMs = Math.min(this.backoffMs * 2, 15000);
  }

  subscribe(channel: string, listener: Listener): () => void {
    let bucket = this.listeners.get(channel);
    if (!bucket) {
      bucket = new Set();
      this.listeners.set(channel, bucket);
    }
    bucket.add(listener);
    if (!this.channels.has(channel)) {
      this.channels.add(channel);
      if (this.socket?.readyState === WebSocket.OPEN) {
        this.socket.send(JSON.stringify({ action: "subscribe", channels: [channel] }));
      }
    }
    return () => {
      bucket.delete(listener);
      if (bucket.size === 0) {
        this.listeners.delete(channel);
        this.channels.delete(channel);
        if (this.socket?.readyState === WebSocket.OPEN) {
          this.socket.send(JSON.stringify({ action: "unsubscribe", channels: [channel] }));
        }
      }
    };
  }

  close(): void {
    this.closed = true;
    this.socket?.close();
    this.socket = null;
  }
}

export const liveChannel = new LiveChannel();
