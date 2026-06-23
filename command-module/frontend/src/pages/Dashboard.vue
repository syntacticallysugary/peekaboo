<script setup lang="ts">
import { onMounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import StatusBadge from "../components/StatusBadge.vue";
import { useWebSocket } from "../composables/useWebSocket";

interface HealthData {
  status: string;
  inference_node: { status: string; gpu_available?: boolean; model_pack?: string };
}
interface Camera {
  camera_id: string;
  type: string;
  ip: string | null;
  status: string;
  last_seen: string | null;
}

const router  = useRouter();
const health  = ref<HealthData | null>(null);
const cameras = ref<Camera[]>([]);
const armed       = ref<boolean | null>(null);
const armingBusy  = ref(false);
const { messages, connected } = useWebSocket("/ws/dashboard");

// Register form
const showRegister  = ref(false);
const regId         = ref("");
const regType       = ref("eye");
const regIp         = ref("");
const registering   = ref(false);
const registerError = ref("");

function timeAgo(iso: string | null): string {
  if (!iso) return "never";
  const diff = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (diff < 60)   return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  return `${Math.floor(diff / 3600)}h ago`;
}

async function loadCameras() {
  cameras.value = await fetch("/api/cameras").then((r) => r.json()).catch(() => []);
}

async function loadArmed() {
  const data = await fetch("/api/system/status").then((r) => r.json()).catch(() => null);
  armed.value = data?.armed ?? null;
}

async function toggleArmed() {
  if (armed.value === null || armingBusy.value) return;
  armingBusy.value = true;
  const action = armed.value ? "disarm" : "arm";
  const res = await fetch(`/api/system/${action}`, { method: "POST" });
  if (res.ok) {
    const data = await res.json();
    armed.value = data.armed;
  }
  armingBusy.value = false;
}

async function registerCamera() {
  if (!regId.value.trim()) return;
  registering.value   = true;
  registerError.value = "";
  const res = await fetch("/api/cameras/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      camera_id:  regId.value.trim(),
      type:       regType.value,
      ip:         regIp.value.trim() || null,
      stream_url: null,
    }),
  });
  registering.value = false;
  if (res.ok) {
    regId.value       = "";
    regIp.value       = "";
    showRegister.value = false;
    await loadCameras();
  } else {
    const d = await res.json().catch(() => ({}));
    registerError.value = (d as { detail?: string }).detail ?? `Error ${res.status}`;
  }
}

onMounted(async () => {
  health.value = await fetch("/health").then((r) => r.json()).catch(() => null);
  await loadCameras();
  await loadArmed();
});

watch(messages, (msgs) => {
  const t = msgs[0]?.type as string | undefined;
  if (t === "detection_event" || t === "session_alert" || t === "camera_status") {
    loadCameras();
  }
  if (t === "system_state") {
    armed.value = msgs[0]?.armed as boolean;
  }
});

const jetsonOk = () => health.value?.inference_node?.status === "ok";
</script>

<template>
  <div style="display:flex;flex-direction:column;gap:3rem">

    <!-- Header -->
    <div style="display:flex;align-items:flex-end;justify-content:space-between;gap:1.5rem;flex-wrap:wrap">
      <div>
        <p class="eyebrow">System</p>
        <div class="eyebrow-bar" />
        <h2 style="font-size:2rem;margin-top:1.25rem">Dashboard</h2>
      </div>
      <div style="display:flex;align-items:center;gap:0.85rem">
        <StatusBadge :value="armed === null ? 'offline' : (armed ? 'armed' : 'disarmed')" />
        <button
          class="btn-primary"
          :style="{ background: armed ? 'var(--color-error)' : 'var(--color-success)' }"
          :disabled="armed === null || armingBusy"
          @click="toggleArmed"
        >
          {{ armingBusy ? "…" : (armed ? "Disarm" : "Arm") }}
        </button>
      </div>
    </div>

    <!-- Health strip -->
    <div style="display:flex;gap:1rem;flex-wrap:wrap">
      <div v-for="item in [
        { label: 'Command Module', ok: health?.status === 'ok', detail: health ? 'FastAPI + LangGraph' : 'connecting…' },
        { label: 'Inference (Jetson)', ok: jetsonOk(), detail: jetsonOk() ? `${health?.inference_node.model_pack ?? 'InsightFace'}${health?.inference_node.gpu_available ? ' · GPU' : ''}` : 'unreachable' },
        { label: 'WebSocket', ok: connected, detail: connected ? 'live' : 'reconnecting…' },
      ]" :key="item.label" class="card" style="flex:1 1 220px;display:flex;flex-direction:column;gap:0.5rem">
        <div style="display:flex;align-items:center;gap:0.6rem">
          <span :class="`status-dot ${item.ok ? 'online' : 'offline'}`" />
          <span style="font-weight:600;font-size:0.9rem">{{ item.label }}</span>
        </div>
        <span style="font-size:0.8rem;color:var(--color-muted);font-family:var(--font-mono)">{{ item.detail }}</span>
      </div>
    </div>

    <hr class="section-divider" style="margin:0" />

    <!-- Cameras -->
    <div>
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:0.5rem">
        <div>
          <p class="eyebrow">Cameras</p>
          <div class="eyebrow-bar" />
        </div>
        <button class="btn-secondary" style="font-size:0.8rem" @click="showRegister = !showRegister">
          {{ showRegister ? "Cancel" : "+ Register Camera" }}
        </button>
      </div>

      <!-- Register form -->
      <div v-if="showRegister" class="card" style="max-width:520px;margin-top:1.25rem;display:flex;flex-direction:column;gap:1rem">
        <p style="font-family:var(--font-mono);font-size:0.65rem;letter-spacing:0.1em;text-transform:uppercase;color:var(--color-muted)">
          New Camera
        </p>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:0.75rem">
          <div style="display:flex;flex-direction:column;gap:0.35rem">
            <label style="font-size:0.78rem;color:var(--color-muted)">Camera ID</label>
            <input v-model="regId" type="text" placeholder="xiao-01" @keydown.enter="registerCamera" />
          </div>
          <div style="display:flex;flex-direction:column;gap:0.35rem">
            <label style="font-size:0.78rem;color:var(--color-muted)">Type</label>
            <select v-model="regType">
              <option value="eye">eye (ESP32 / XIAO)</option>
              <option value="cam">cam (IP camera)</option>
            </select>
          </div>
        </div>
        <div style="display:flex;flex-direction:column;gap:0.35rem">
          <label style="font-size:0.78rem;color:var(--color-muted)">IP Address <span style="opacity:0.5">(optional)</span></label>
          <input v-model="regIp" type="text" placeholder="192.168.1.x" @keydown.enter="registerCamera" />
        </div>
        <div style="display:flex;align-items:center;gap:0.75rem">
          <button class="btn-primary" :disabled="registering || !regId.trim()" @click="registerCamera">
            {{ registering ? "Registering…" : "Register" }}
          </button>
          <span v-if="registerError" style="font-size:0.8rem;color:var(--color-error);font-family:var(--font-mono)">
            {{ registerError }}
          </span>
        </div>
      </div>

      <!-- Camera grid -->
      <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:1.25rem;margin-top:1.75rem">
        <p v-if="cameras.length === 0 && !showRegister" style="color:var(--color-muted);font-size:0.9rem">
          No cameras registered.
        </p>
        <div
          v-for="cam in cameras" :key="cam.camera_id"
          class="card" style="display:flex;flex-direction:column;gap:0.75rem;cursor:pointer"
          @click="router.push(`/cameras/${cam.camera_id}`)"
        >
          <div style="display:flex;justify-content:space-between;align-items:flex-start">
            <div>
              <div style="font-weight:600;font-size:0.95rem">{{ cam.camera_id }}</div>
              <div style="font-family:var(--font-mono);font-size:0.72rem;color:var(--color-muted);margin-top:0.2rem">
                {{ cam.ip ?? "no ip" }} · {{ cam.type }}
              </div>
            </div>
            <StatusBadge :value="cam.status === 'connected' ? 'online' : 'offline'" />
          </div>
          <div style="font-size:0.78rem;color:var(--color-muted)">Last seen: {{ timeAgo(cam.last_seen) }}</div>
        </div>
      </div>
    </div>

    <hr class="section-divider" style="margin:0" />

    <!-- Live event feed -->
    <div>
      <p class="eyebrow">Live Feed</p>
      <div class="eyebrow-bar" />
      <div style="margin-top:1.75rem;display:flex;flex-direction:column;gap:0.75rem">
        <p v-if="messages.length === 0" style="color:var(--color-muted);font-size:0.9rem">
          {{ connected ? "Waiting for events…" : "Connecting to live feed…" }}
        </p>
        <div
          v-for="(msg, i) in messages.slice(0, 20)" :key="i"
          class="card"
          style="padding:1rem 1.5rem;display:flex;align-items:center;gap:1.25rem;cursor:pointer"
          @click="msg.event_id && router.push(`/events/${msg.event_id}`)"
        >
          <StatusBadge :value="String(msg.classification ?? 'unknown')" />
          <span style="font-family:var(--font-mono);font-size:0.8rem;color:var(--color-muted)">{{ String(msg.camera_id ?? "—") }}</span>
          <span v-if="msg.person_name" style="font-size:0.85rem;color:var(--color-soft)">{{ String(msg.person_name) }}</span>
          <span style="margin-left:auto;font-size:0.75rem;color:var(--color-muted);font-family:var(--font-mono)">
            {{ msg.detected_at ? new Date(String(msg.detected_at)).toLocaleTimeString() : "now" }}
          </span>
        </div>
      </div>
    </div>

  </div>
</template>
