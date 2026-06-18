<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
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

interface Person {
  person_id: string;
  name: string;
}

const route   = useRoute();
const router  = useRouter();
const eventId = route.params.eventId as string;

const event        = ref<DetectionEvent | null>(null);
const videoUrl     = ref<string | null>(null);
const loading      = ref(true);
const videoError   = ref(false);

const persons         = ref<Person[]>([]);
const selectedPerson  = ref<string>("");
const identifying     = ref(false);
const identifyError   = ref<string | null>(null);
const identifySuccess = ref(false);

onMounted(async () => {
  const [all, ppl] = await Promise.all([
    fetch(`/api/events?limit=500`).then((r) => r.json()).catch(() => []),
    fetch(`/api/persons`).then((r) => r.json()).catch(() => []),
  ]);

  event.value = (all as DetectionEvent[]).find((e) => e.event_id === eventId) ?? null;
  persons.value = ppl as Person[];

  if (event.value?.recording_path) {
    videoUrl.value = `/proxy/recordings/${event.value.recording_path}`;
  }

  loading.value = false;
});

async function identify() {
  if (!selectedPerson.value) return;
  identifying.value = true;
  identifyError.value = null;
  try {
    const resp = await fetch(`/api/events/${eventId}/identify`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ person_id: selectedPerson.value }),
    });
    if (!resp.ok) {
      const detail = await resp.json().catch(() => ({}));
      throw new Error(detail.detail ?? `HTTP ${resp.status}`);
    }
    identifySuccess.value = true;
    if (event.value) {
      event.value.classification = "known";
      event.value.person_id = selectedPerson.value;
    }
  } catch (err: any) {
    identifyError.value = err.message ?? "Identification failed";
  } finally {
    identifying.value = false;
  }
}
</script>

<template>
  <div style="display:flex;flex-direction:column;gap:3rem">

    <!-- Back + header -->
    <div>
      <button class="btn-secondary" style="font-size:0.8rem;margin-bottom:1.5rem" @click="router.back()">← Back</button>
      <p class="eyebrow">Alert Detail</p>
      <div class="eyebrow-bar" />
      <h2 style="font-size:2rem;margin-top:1.25rem">Event</h2>
    </div>

    <div v-if="loading" style="color:var(--color-muted);font-size:0.9rem">Loading…</div>

    <div v-else-if="!event" class="card" style="text-align:center;color:var(--color-muted);padding:3rem">
      Event not found.
    </div>

    <template v-else>

      <!-- Event metadata -->
      <div style="display:flex;gap:1rem;flex-wrap:wrap">
        <div class="card" style="flex:1 1 200px;display:flex;flex-direction:column;gap:0.5rem">
          <span style="font-family:var(--font-mono);font-size:0.65rem;letter-spacing:0.1em;text-transform:uppercase;color:var(--color-muted)">Classification</span>
          <StatusBadge :value="event.classification" />
        </div>
        <div class="card" style="flex:1 1 200px;display:flex;flex-direction:column;gap:0.5rem">
          <span style="font-family:var(--font-mono);font-size:0.65rem;letter-spacing:0.1em;text-transform:uppercase;color:var(--color-muted)">Camera</span>
          <span
            style="font-size:0.9rem;font-weight:600;color:var(--color-accent);cursor:pointer"
            @click="router.push(`/cameras/${event!.camera_id}`)"
          >{{ event.camera_id }} ↗</span>
        </div>
        <div class="card" style="flex:1 1 200px;display:flex;flex-direction:column;gap:0.5rem">
          <span style="font-family:var(--font-mono);font-size:0.65rem;letter-spacing:0.1em;text-transform:uppercase;color:var(--color-muted)">Timestamp</span>
          <span style="font-size:0.9rem;font-weight:600">{{ new Date(event.detected_at).toLocaleString() }}</span>
        </div>
        <div v-if="event.confidence != null" class="card" style="flex:1 1 200px;display:flex;flex-direction:column;gap:0.5rem">
          <span style="font-family:var(--font-mono);font-size:0.65rem;letter-spacing:0.1em;text-transform:uppercase;color:var(--color-muted)">{{ event.person_id ? "Confidence" : "Best Match Score" }}</span>
          <span style="font-size:0.9rem;font-weight:600">{{ (event.confidence * 100).toFixed(1) }}%</span>
        </div>
      </div>

      <!-- Footage -->
      <div>
        <p class="eyebrow">Footage</p>
        <div class="eyebrow-bar" />
        <div style="margin-top:1.5rem">
          <div v-if="!event.recording_path" class="card" style="padding:3rem;text-align:center;color:var(--color-muted);font-size:0.9rem">
            No recording associated with this event.
          </div>
          <div v-else-if="!videoUrl" class="card" style="padding:3rem;text-align:center;color:var(--color-muted);font-size:0.9rem">
            No recording URL available.
          </div>
          <div v-else-if="videoError" class="card" style="padding:3rem;text-align:center;color:var(--color-muted);font-size:0.9rem">
            Could not load recording — the Jetson may be unreachable or the clip was deleted.
          </div>
          <div v-else style="border-radius:12px;overflow:hidden;border:1px solid var(--color-border);max-width:800px">
            <video
              :src="videoUrl"
              controls
              style="width:100%;display:block;background:#000"
              @error="videoError = true"
            />
          </div>
          <p v-if="event.recording_path" style="font-size:0.72rem;color:var(--color-muted);font-family:var(--font-mono);margin-top:0.75rem">
            {{ event.recording_path }}
          </p>
        </div>
      </div>

      <!-- Identify panel — only for unknown events -->
      <div v-if="event.classification === 'unknown' || event.classification === 'no_face'">
        <p class="eyebrow">Identify</p>
        <div class="eyebrow-bar" />
        <div style="margin-top:1.5rem">
          <div v-if="identifySuccess" class="card" style="padding:1.5rem;color:#4ade80;font-size:0.9rem">
            Identified and enrolled. Future sessions from this camera will recognize them automatically.
          </div>
          <div v-else class="card" style="padding:1.5rem;display:flex;flex-direction:column;gap:1rem">
            <p style="font-size:0.85rem;color:var(--color-muted);margin:0">
              Recognize someone in this footage? Mark them as a known person to enroll this camera angle.
            </p>
            <div style="display:flex;gap:0.75rem;align-items:center;flex-wrap:wrap">
              <select
                v-model="selectedPerson"
                style="padding:0.5rem 0.75rem;background:var(--color-surface);border:1px solid var(--color-border);border-radius:6px;color:var(--color-text);font-size:0.9rem;min-width:180px"
              >
                <option value="">Select person…</option>
                <option v-for="p in persons" :key="p.person_id" :value="p.person_id">
                  {{ p.name }}
                </option>
              </select>
              <button
                class="btn-primary"
                :disabled="!selectedPerson || identifying"
                @click="identify"
                style="font-size:0.85rem;padding:0.5rem 1.25rem"
              >
                {{ identifying ? "Identifying…" : "This is them" }}
              </button>
            </div>
            <p v-if="identifyError" style="color:#f87171;font-size:0.8rem;margin:0">{{ identifyError }}</p>
          </div>
        </div>
      </div>

    </template>

  </div>
</template>
