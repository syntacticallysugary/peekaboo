<script setup lang="ts">
import { onMounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import StatusBadge from "../components/StatusBadge.vue";

interface DetectionEvent {
  event_id: string;
  camera_id: string;
  detected_at: string;
  classification: string;
  person_id: string | null;
  confidence: number | null;
  recording_path: string | null;
}

const router  = useRouter();
const events  = ref<DetectionEvent[]>([]);
const loading = ref(true);
const filter  = ref("");

async function load() {
  loading.value = true;
  const params = new URLSearchParams({ limit: "100" });
  if (filter.value) params.set("classification", filter.value);
  events.value = await fetch(`/api/events?${params}`).then((r) => r.json()).catch(() => []);
  loading.value = false;
}

onMounted(load);
watch(filter, load);
</script>

<template>
  <div style="display:flex;flex-direction:column;gap:2.5rem">

    <div>
      <p class="eyebrow">History</p>
      <div class="eyebrow-bar" />
      <h2 style="font-size:2rem;margin-top:1.25rem">Detection Events</h2>
    </div>

    <div style="display:flex;gap:0.75rem;align-items:center">
      <select v-model="filter" style="max-width:220px">
        <option value="">All classifications</option>
        <option value="unknown">Unknown</option>
        <option value="known">Authorized</option>
        <option value="unallowed">Blocked</option>
        <option value="no_face">No face</option>
      </select>
      <button class="btn-secondary" @click="load">Refresh</button>
    </div>

    <div style="overflow-x:auto">
      <table style="width:100%;border-collapse:collapse;font-size:0.875rem">
        <thead>
          <tr style="border-bottom:1px solid var(--color-border)">
            <th v-for="h in ['Time','Camera','Classification','Confidence','Recording']" :key="h"
              style="padding:0.65rem 1rem;text-align:left;font-family:var(--font-mono);font-size:0.65rem;letter-spacing:0.1em;text-transform:uppercase;color:var(--color-muted);font-weight:500">
              {{ h }}
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="loading">
            <td colspan="5" style="padding:2rem 1rem;color:var(--color-muted);text-align:center">Loading…</td>
          </tr>
          <tr v-else-if="events.length === 0">
            <td colspan="5" style="padding:2rem 1rem;color:var(--color-muted);text-align:center">No events found.</td>
          </tr>
          <tr
            v-for="(ev, i) in events" :key="ev.event_id"
            style="cursor:pointer;transition:background 0.15s"
            :style="{ borderBottom: '1px solid var(--color-border)', background: i % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.015)' }"
            @click="router.push(`/events/${ev.event_id}`)"
          >
            <td style="padding:0.75rem 1rem;font-family:var(--font-mono);font-size:0.78rem;color:var(--color-muted);white-space:nowrap">
              {{ new Date(ev.detected_at).toLocaleString() }}
            </td>
            <td style="padding:0.75rem 1rem;font-family:var(--font-mono);font-size:0.8rem">{{ ev.camera_id }}</td>
            <td style="padding:0.75rem 1rem"><StatusBadge :value="ev.classification" /></td>
            <td style="padding:0.75rem 1rem;font-family:var(--font-mono);font-size:0.78rem;color:var(--color-muted)">
              {{ ev.confidence != null ? `${(ev.confidence * 100).toFixed(1)}%` : "—" }}
            </td>
            <td style="padding:0.75rem 1rem">
              <span v-if="ev.recording_path" style="color:var(--color-accent);font-size:0.8rem">view ↗</span>
              <span v-else style="color:var(--color-muted);font-size:0.78rem">—</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

  </div>
</template>
