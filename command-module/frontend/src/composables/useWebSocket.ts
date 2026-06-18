import { onUnmounted, ref } from "vue";

export type WsMessage = Record<string, unknown>;

export function useWebSocket(path: string) {
  const messages  = ref<WsMessage[]>([]);
  const connected = ref(false);

  let ws: WebSocket | null = null;
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

  function connect() {
    const protocol = window.location.protocol === "https:" ? "wss" : "ws";
    const socket = new WebSocket(`${protocol}://${window.location.host}${path}`);
    ws = socket;

    socket.onopen  = () => { connected.value = true; };
    socket.onclose = () => {
      connected.value = false;
      reconnectTimer = setTimeout(connect, 3000);
    };
    socket.onerror = () => socket.close();
    socket.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data) as WsMessage;
        messages.value = [data, ...messages.value].slice(0, 100);
      } catch { /* ignore malformed */ }
    };
  }

  connect();

  onUnmounted(() => {
    ws?.close();
    if (reconnectTimer) clearTimeout(reconnectTimer);
  });

  return { messages, connected };
}
