<script setup lang="ts">
import { onMounted, ref } from "vue";

interface FirmwareChannel {
  channel: string;
  version: string | null;
  size: number | null;
  updated_at: string | null;
}
interface Webhook {
  webhook_id: string;
  url: string;
  active: boolean;
}

const firmware       = ref<FirmwareChannel[]>([]);
const fwVersion       = ref("");
const fwFile          = ref<HTMLInputElement | null>(null);
const uploadingChannel = ref<string | null>(null);
const uploadMsg        = ref("");
const uploadError      = ref(false);

const webhooks    = ref<Webhook[]>([]);
const newUrl      = ref("");
const newSecret   = ref("");
const creatingHook = ref(false);
const hookError    = ref("");

const scheduleEnabled = ref(false);
const armTime         = ref("");
const disarmTime      = ref("");
const savingSchedule  = ref(false);
const scheduleMsg     = ref("");
const scheduleError   = ref(false);

function formatSize(bytes: number | null): string {
  if (bytes == null) return "—";
  return `${(bytes / 1024).toFixed(0)} KB`;
}

async function loadFirmware() {
  firmware.value = await fetch("/api/firmware").then((r) => r.json()).catch(() => []);
}

function triggerUpload(channel: string) {
  if (!fwVersion.value.trim()) {
    uploadError.value = true;
    uploadMsg.value = "Enter a version string first.";
    return;
  }
  uploadingChannel.value = channel;
  fwFile.value?.click();
}

async function handleFirmwareFile(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0];
  const channel = uploadingChannel.value;
  if (!file || !channel) return;

  uploadError.value = false;
  uploadMsg.value = `Uploading ${file.name}…`;
  const body = await file.arrayBuffer();
  const res = await fetch(`/api/firmware/${channel}`, {
    method: "POST",
    headers: {
      "X-Firmware-Version": fwVersion.value.trim(),
      "Content-Type": "application/octet-stream",
    },
    body,
  });
  if (res.ok) {
    const data = await res.json();
    uploadMsg.value = `${channel}: uploaded version ${data.version} (${formatSize(data.size)})`;
    fwVersion.value = "";
    await loadFirmware();
  } else {
    const data = await res.json().catch(() => ({}));
    uploadError.value = true;
    uploadMsg.value = (data as { detail?: string }).detail ?? `Upload failed (${res.status})`;
  }
  (e.target as HTMLInputElement).value = "";
  uploadingChannel.value = null;
}

async function loadWebhooks() {
  webhooks.value = await fetch("/api/webhooks").then((r) => r.json()).catch(() => []);
}

async function createWebhook() {
  if (!newUrl.value.trim()) return;
  creatingHook.value = true;
  hookError.value = "";
  const res = await fetch("/api/webhooks", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url: newUrl.value.trim(), secret: newSecret.value.trim() || null }),
  });
  creatingHook.value = false;
  if (res.ok) {
    newUrl.value = "";
    newSecret.value = "";
    await loadWebhooks();
  } else {
    const data = await res.json().catch(() => ({}));
    hookError.value = (data as { detail?: string }).detail ?? `Error ${res.status}`;
  }
}

async function deleteWebhook(id: string) {
  if (!confirm("Delete this webhook?")) return;
  await fetch(`/api/webhooks/${id}`, { method: "DELETE" });
  await loadWebhooks();
}

async function loadSchedule() {
  const data = await fetch("/api/system/schedule").then((r) => r.json()).catch(() => null);
  if (data) {
    scheduleEnabled.value = data.enabled ?? false;
    armTime.value         = data.arm_time ?? "";
    disarmTime.value      = data.disarm_time ?? "";
  }
}

async function saveSchedule() {
  savingSchedule.value = true;
  scheduleError.value  = false;
  const res = await fetch("/api/system/schedule", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      enabled: scheduleEnabled.value,
      arm_time: armTime.value || null,
      disarm_time: disarmTime.value || null,
    }),
  });
  savingSchedule.value = false;
  if (res.ok) {
    scheduleMsg.value = "Schedule saved.";
  } else {
    const data = await res.json().catch(() => ({}));
    scheduleError.value = true;
    scheduleMsg.value = (data as { detail?: string }).detail ?? `Error ${res.status}`;
  }
}

onMounted(async () => {
  await loadFirmware();
  await loadWebhooks();
  await loadSchedule();
});
</script>

<template>
  <div style="display:flex;flex-direction:column;gap:3rem">

    <input ref="fwFile" type="file" accept=".bin" style="display:none" @change="handleFirmwareFile" />

    <div>
      <p class="eyebrow">Configuration</p>
      <div class="eyebrow-bar" />
      <h2 style="font-size:2rem;margin-top:1.25rem">Settings</h2>
    </div>

    <!-- Firmware -->
    <div>
      <p class="eyebrow">Firmware (OTA)</p>
      <div class="eyebrow-bar" />
      <p style="color:var(--color-muted);margin-top:0.75rem;font-size:0.9rem">
        Cameras poll their channel every 5 minutes and pull a new binary automatically when the version changes.
      </p>

      <div class="card" style="max-width:420px;margin-top:1.25rem">
        <label style="font-size:0.78rem;color:var(--color-muted)">Version to assign on next upload</label>
        <input v-model="fwVersion" type="text" placeholder="1.1.0" style="margin-top:0.4rem" />
      </div>

      <div style="display:flex;flex-direction:column;gap:1rem;margin-top:1.5rem">
        <div v-for="fw in firmware" :key="fw.channel" class="card" style="display:flex;align-items:center;gap:1.5rem;flex-wrap:wrap">
          <div style="flex:1;min-width:160px">
            <div style="font-weight:600;font-size:0.95rem">{{ fw.channel }}</div>
            <div style="font-family:var(--font-mono);font-size:0.72rem;color:var(--color-muted);margin-top:0.25rem">
              <template v-if="fw.version">
                v{{ fw.version }} · {{ formatSize(fw.size) }} · {{ new Date(fw.updated_at!).toLocaleString() }}
              </template>
              <template v-else>no firmware uploaded yet</template>
            </div>
          </div>
          <button class="btn-secondary" style="font-size:0.8rem" @click="triggerUpload(fw.channel)">
            Upload .bin
          </button>
        </div>
      </div>

      <p v-if="uploadMsg" :style="{
        marginTop: '1rem', fontSize: '0.85rem', fontFamily: 'var(--font-mono)',
        color: uploadError ? 'var(--color-error)' : 'var(--color-success)'
      }">{{ uploadMsg }}</p>
    </div>

    <hr class="section-divider" style="margin:0" />

    <!-- Arm/Disarm schedule -->
    <div>
      <p class="eyebrow">Arm / Disarm Schedule</p>
      <div class="eyebrow-bar" />
      <p style="color:var(--color-muted);margin-top:0.75rem;font-size:0.9rem">
        Optional. Times are server-local, 24-hour. A manual Arm/Disarm on the dashboard always takes
        effect immediately — the schedule only acts at these two times, so it won't fight a manual
        change made in between.
      </p>

      <div class="card" style="max-width:420px;margin-top:1.25rem;display:flex;flex-direction:column;gap:1rem">
        <label style="display:flex;align-items:center;gap:0.6rem;font-size:0.9rem">
          <input type="checkbox" v-model="scheduleEnabled" />
          Enable schedule
        </label>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:0.75rem">
          <div style="display:flex;flex-direction:column;gap:0.35rem">
            <label style="font-size:0.78rem;color:var(--color-muted)">Arm at</label>
            <input v-model="armTime" type="time" :disabled="!scheduleEnabled" />
          </div>
          <div style="display:flex;flex-direction:column;gap:0.35rem">
            <label style="font-size:0.78rem;color:var(--color-muted)">Disarm at</label>
            <input v-model="disarmTime" type="time" :disabled="!scheduleEnabled" />
          </div>
        </div>
        <div style="display:flex;align-items:center;gap:0.75rem">
          <button class="btn-primary" :disabled="savingSchedule" @click="saveSchedule">
            {{ savingSchedule ? "Saving…" : "Save Schedule" }}
          </button>
          <span v-if="scheduleMsg" :style="{
            fontSize: '0.8rem', fontFamily: 'var(--font-mono)',
            color: scheduleError ? 'var(--color-error)' : 'var(--color-success)'
          }">{{ scheduleMsg }}</span>
        </div>
      </div>
    </div>

    <hr class="section-divider" style="margin:0" />

    <!-- Webhooks -->
    <div>
      <p class="eyebrow">Webhooks</p>
      <div class="eyebrow-bar" />
      <p style="color:var(--color-muted);margin-top:0.75rem;font-size:0.9rem">
        Every detection event is POSTed to all active webhook URLs. Set a secret to receive an
        <code>X-Peekaboo-Signature</code> HMAC header for verification.
      </p>

      <div class="card" style="max-width:480px;margin-top:1.25rem;display:flex;flex-direction:column;gap:0.75rem">
        <div style="display:flex;flex-direction:column;gap:0.35rem">
          <label style="font-size:0.78rem;color:var(--color-muted)">URL</label>
          <input v-model="newUrl" type="text" placeholder="https://example.com/peekaboo-hook" @keydown.enter="createWebhook" />
        </div>
        <div style="display:flex;flex-direction:column;gap:0.35rem">
          <label style="font-size:0.78rem;color:var(--color-muted)">Secret <span style="opacity:0.5">(optional)</span></label>
          <input v-model="newSecret" type="text" placeholder="shared signing secret" @keydown.enter="createWebhook" />
        </div>
        <div style="display:flex;align-items:center;gap:0.75rem">
          <button class="btn-primary" :disabled="creatingHook || !newUrl.trim()" @click="createWebhook">
            {{ creatingHook ? "Adding…" : "Add Webhook" }}
          </button>
          <span v-if="hookError" style="font-size:0.8rem;color:var(--color-error);font-family:var(--font-mono)">{{ hookError }}</span>
        </div>
      </div>

      <p v-if="webhooks.length === 0" style="color:var(--color-muted);font-size:0.9rem;margin-top:1.5rem">
        No webhooks registered.
      </p>
      <div style="display:flex;flex-direction:column;gap:1rem;margin-top:1.5rem">
        <div v-for="wh in webhooks" :key="wh.webhook_id" class="card" style="display:flex;align-items:center;gap:1.5rem;flex-wrap:wrap">
          <div style="flex:1;min-width:200px">
            <div style="font-family:var(--font-mono);font-size:0.85rem;word-break:break-all">{{ wh.url }}</div>
            <span class="badge" :class="wh.active ? 'badge-known' : 'badge-no_face'" style="margin-top:0.4rem">
              {{ wh.active ? "active" : "inactive" }}
            </span>
          </div>
          <button class="btn-danger" style="font-size:0.8rem" @click="deleteWebhook(wh.webhook_id)">Delete</button>
        </div>
      </div>
    </div>

  </div>
</template>
