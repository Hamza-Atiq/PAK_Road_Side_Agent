// Tiny WebSocket helper. App provides the base URL + token; we manage reconnect.
//
// The backend uses ws://HOST/ws/incidents/<id> with bearer-style token in query.

export interface WSOptions {
  url: string;
  token?: string | null;
  onMessage: (msg: unknown) => void;
  onOpen?: () => void;
  onClose?: (ev: CloseEvent) => void;
  onError?: (ev: Event) => void;
}

export interface WSHandle {
  close: () => void;
  send: (data: unknown) => void;
}

export function connectWS({
  url,
  token,
  onMessage,
  onOpen,
  onClose,
  onError,
}: WSOptions): WSHandle {
  const u = new URL(url);
  if (token) u.searchParams.set("token", token);
  const ws = new WebSocket(u.toString());

  ws.addEventListener("open", () => onOpen?.());
  ws.addEventListener("close", (ev) => onClose?.(ev));
  ws.addEventListener("error", (ev) => onError?.(ev));
  ws.addEventListener("message", (ev) => {
    try {
      onMessage(JSON.parse(String(ev.data)));
    } catch {
      onMessage(ev.data);
    }
  });

  return {
    close: () => {
      try {
        ws.close(1000, "client closed");
      } catch {
        /* ignore */
      }
    },
    send: (data) => {
      try {
        ws.send(typeof data === "string" ? data : JSON.stringify(data));
      } catch {
        /* ignore */
      }
    },
  };
}
