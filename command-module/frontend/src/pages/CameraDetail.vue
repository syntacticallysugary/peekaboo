<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import StatusBadge from "../components/StatusBadge.vue";
import { useWebSocket } from "../composables/useWebSocket";

interface Camera {
  camera_id: string;
  type: string;
  ip: string | null;
  stream_url: string | null;
  status: string;
  last_seen: string | null;
}
interface DetectionEvent {
  event_id: string;
  camera_id: string;
  detected_at: string;
  classification: string;
  confidence: number | null;
  recording_path: string | null;
}

const route  = useRoute();
const router = useRouter();
const cameraId = route.params.cameraId as string;

const camera      = ref<Camera | null>(null);
const events      = ref<DetectionEvent[]>([]);
const feedErr     = ref(false);
const snapshotSrc = ref<string | null>(null);

let _pollTimer: ReturnType<typeof setInterval> | null = null;
let _failCount = 0;

// Edit form
const editIp    = ref("");
const saving    = ref(false);
const saveError = ref("");

// MQTT control
const rebooting = ref(false);
const diagBusy  = ref(false);
const controlMsg = ref("");
const controlError = ref(false);
const diag = ref<Record<string, unknown> | null>(null);

const { messages } = useWebSocket("/ws/dashboard");

function timeAgo(iso: string | null): string {
  if (!iso) return "never";
  const diff = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (diff < 60)   return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  return `${Math.floor(diff / 3600)}h ago`;
}

async function loadCamera() {
  const all: Camera[] = await fetch("/api/cameras").then((r) => r.json()).catch(() => []);
  camera.value = all.find((c) => c.camera_id === cameraId) ?? null;
  if (camera.value) editIp.value = camera.value.ip ?? "";
}

async function saveIp() {
  if (!camera.value) return;
  saving.value   = true;
  saveError.value = "";
  const res = await fetch("/api/cameras/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      camera_id:  camera.value.camera_id,
      type:       camera.value.type,
      ip:         editIp.value.trim() || null,
      stream_url: camera.value.stream_url,
    }),
  });
  saving.value = false;
  if (res.ok) {
    feedErr.value = false;
    await loadCamera();
  } else {
    saveError.value = `Error ${res.status}`;
  }
}

async function rebootCamera() {
  if (!confirm(`Reboot ${cameraId}? It will drop offline for a few seconds.`)) return;
  rebooting.value = true;
  controlError.value = false;
  controlMsg.value = "";
  const res = await fetch(`/api/cameras/${cameraId}/reboot`, { method: "POST" });
  rebooting.value = false;
  if (res.ok) {
    controlMsg.value = "Reboot command sent.";
  } else {
    const data = await res.json().catch(() => ({}));
    controlError.value = true;
    controlMsg.value = (data as { detail?: string }).detail ?? `Error ${res.status}`;
  }
}

async function runDiag() {
  diagBusy.value = true;
  controlError.value = false;
  controlMsg.value = "Requesting diagnostics…";
  const res = await fetch(`/api/cameras/${cameraId}/diag`, { method: "POST" });
  diagBusy.value = false;
  if (res.ok) {
    diag.value = await res.json();
    controlMsg.value = "";
  } else {
    const data = await res.json().catch(() => ({}));
    controlError.value = true;
    controlMsg.value = (data as { detail?: string }).detail ?? `Error ${res.status}`;
  }
}

async function loadEvents() {
  const params = new URLSearchParams({ camera_id: cameraId, limit: "10" });
  events.value = await fetch(`/api/events?${params}`).then((r) => r.json()).catch(() => []);
}

async function fetchSnapshot() {
  try {
    const res = await fetch(`/proxy/snapshot/${cameraId}`);
    if (res.ok) {
      const blob = await res.blob();
      const next = URL.createObjectURL(blob);
      if (snapshotSrc.value?.startsWith("blob:")) URL.revokeObjectURL(snapshotSrc.value);
      snapshotSrc.value = next;
      _failCount = 0;
    } else if (res.status !== 503) {
      if (++_failCount >= 3) feedErr.value = true;
    }
  } catch {
    if (++_failCount >= 3) feedErr.value = true;
  }
}

onMounted(async () => {
  await Promise.all([loadCamera(), loadEvents()]);
  await fetchSnapshot();
  _pollTimer = setInterval(fetchSnapshot, 500);
});

onUnmounted(() => {
  if (_pollTimer) clearInterval(_pollTimer);
  if (snapshotSrc.value?.startsWith("blob:")) URL.revokeObjectURL(snapshotSrc.value);
});

watch(messages, (msgs) => {
  const msg = msgs[0];
  if (msg?.camera_id === cameraId) loadEvents();
  if (msg?.type === "camera_status" && msg?.camera_id === cameraId) loadCamera();
});
</script>

<template>
  <div style="display:flex;flex-direction:column;gap:3rem">

    <!-- Back + header -->
    <div>
      <button class="btn-secondary" style="font-size:0.8rem;margin-bottom:1.5rem" @click="router.back()">← Back</button>
      <p class="eyebrow">Camera</p>
      <div class="eyebrow-bar" />
      <div style="display:flex;align-items:center;gap:1rem;margin-top:1.25rem">
        <h2 style="font-size:2rem">{{ cameraId }}</h2>
        <StatusBadge v-if="camera" :value="camera.status === 'connected' ? 'online' : 'offline'" />
      </div>
      <div v-if="camera" style="font-family:var(--font-mono);font-size:0.78rem;color:var(--color-muted);margin-top:0.4rem">
        {{ camera.type }} · last seen {{ timeAgo(camera.last_seen) }}
      </div>
      <!-- IP edit -->
      <div v-if="camera" style="display:flex;align-items:center;gap:0.6rem;margin-top:0.75rem">
        <input
          v-model="editIp"
          type="text"
          placeholder="192.168.1.x"
          style="max-width:180px;padding:0.4rem 0.75rem;font-size:0.85rem;font-family:var(--font-mono)"
          @keydown.enter="saveIp"
        />
        <button class="btn-secondary" style="font-size:0.8rem" :disabled="saving" @click="saveIp">
          {{ saving ? "Saving…" : "Save IP" }}
        </button>
        <span v-if="saveError" style="font-size:0.78rem;color:var(--color-error);font-family:var(--font-mono)">{{ saveError }}</span>
      </div>

      <!-- Remote control (over secure MQTT) -->
      <div v-if="camera" style="display:flex;align-items:center;gap:0.6rem;margin-top:0.75rem;flex-wrap:wrap">
        <button class="btn-secondary" style="font-size:0.8rem" :disabled="diagBusy" @click="runDiag">
          {{ diagBusy ? "Querying…" : "Diagnostics" }}
        </button>
        <button class="btn-danger" style="font-size:0.8rem" :disabled="rebooting" @click="rebootCamera">
          {{ rebooting ? "Sending…" : "Reboot" }}
        </button>
        <span v-if="controlMsg" :style="{
          fontSize: '0.78rem', fontFamily: 'var(--font-mono)',
          color: controlError ? 'var(--color-error)' : 'var(--color-success)'
        }">{{ controlMsg }}</span>
      </div>
      <div v-if="diag" class="card" style="margin-top:0.75rem;max-width:420px;font-family:var(--font-mono);font-size:0.75rem;color:var(--color-muted)">
        <div v-for="(val, key) in diag" :key="key" style="display:flex;justify-content:space-between;gap:1rem">
          <span>{{ key }}</span><span style="color:var(--color-text)">{{ val }}</span>
        </div>
      </div>
    </div>

    <!-- Live feed -->
    <div>
      <p class="eyebrow">Live Feed</p>
      <div class="eyebrow-bar" />
      <div style="margin-top:1.5rem">
        <div v-if="feedErr" class="card" style="padding:3rem;text-align:center;color:var(--color-muted);font-size:0.9rem">
          Feed unavailable — ensure you are on the local network or VPN.
        </div>
        <div v-else-if="!snapshotSrc" class="card" style="padding:3rem;text-align:center;color:var(--color-muted);font-size:0.9rem">
          Connecting to camera…
        </div>
        <div v-else style="border-radius:12px;overflow:hidden;border:1px solid var(--color-border);max-width:800px">
          <img
            :src="snapshotSrc"
            alt="live camera feed"
            style="width:100%;display:block"
          />
        </div>
        <p style="font-size:0.75rem;color:var(--color-muted);font-family:var(--font-mono);margin-top:0.75rem">
          Requires local network or WireGuard VPN connection.
        </p>
      </div>
    </div>

    <hr class="section-divider" style="margin:0" />

    <!-- Recent alerts -->
    <div>
      <p class="eyebrow">Recent Alerts</p>
      <div class="eyebrow-bar" />
      <div style="margin-top:1.75rem;display:flex;flex-direction:column;gap:0.75rem">
        <p v-if="events.length === 0" style="color:var(--color-muted);font-size:0.9rem">No events recorded for this camera.</p>
        <div
          v-for="ev in events" :key="ev.event_id"
          class="card" style="padding:1rem 1.5rem;display:flex;align-items:center;gap:1.25rem;cursor:pointer"
          @click="router.push(`/events/${ev.event_id}`)"
        >
          <StatusBadge :value="ev.classification" />
          <span style="font-family:var(--font-mono);font-size:0.78rem;color:var(--color-muted)">
            {{ new Date(ev.detected_at).toLocaleString() }}
          </span>
          <span v-if="ev.confidence != null" style="font-family:var(--font-mono);font-size:0.75rem;color:var(--color-muted)">
            {{ (ev.confidence * 100).toFixed(1) }}%
          </span>
          <span v-if="ev.recording_path" style="margin-left:auto;color:var(--color-accent);font-size:0.8rem">footage ↗</span>
        </div>
      </div>
    </div>

  </div>
</template>
