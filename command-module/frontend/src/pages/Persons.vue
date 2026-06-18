<script setup lang="ts">
import { onMounted, ref } from "vue";

interface Person {
  person_id: string;
  name: string;
  is_blocked: boolean;
  created_at: string;
  embedding_count: number;
}
type EnrollState = "idle" | "waiting" | "done" | "error";

const persons     = ref<Person[]>([]);
const newName     = ref("");
const creating    = ref(false);
const enrollId    = ref<string | null>(null);
const enrollState = ref<EnrollState>("idle");
const enrollMsg   = ref("");
const uploadInput = ref<HTMLInputElement | null>(null);
const uploadingId = ref<string | null>(null);

async function load() {
  persons.value = await fetch("/api/persons").then((r) => r.json()).catch(() => []);
}
onMounted(load);

async function createPerson() {
  if (!newName.value.trim()) return;
  creating.value = true;
  await fetch("/api/persons", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name: newName.value.trim() }),
  });
  newName.value = "";
  creating.value = false;
  load();
}

async function startEnroll(id: string) {
  enrollId.value    = id;
  enrollState.value = "waiting";
  enrollMsg.value   = "Walk toward the camera from the front. Waiting up to 30s…";
  const res = await fetch(`/api/persons/${id}/capture`, { method: "POST" });
  if (res.ok) {
    enrollState.value = "done";
    enrollMsg.value   = "Enrolled successfully.";
    load();
  } else {
    const data = await res.json().catch(() => ({}));
    enrollState.value = "error";
    enrollMsg.value   = (data as { detail?: string }).detail ?? "Enrollment failed.";
  }
}

function clearEnroll() {
  enrollId.value    = null;
  enrollState.value = "idle";
  enrollMsg.value   = "";
}

function triggerUpload(id: string) {
  uploadingId.value = id;
  uploadInput.value?.click();
}

async function handleUpload(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0];
  if (!file || !uploadingId.value) return;
  const id = uploadingId.value;
  const fd = new FormData();
  fd.append("image", file);
  enrollId.value    = id;
  enrollState.value = "waiting";
  enrollMsg.value   = "Uploading photo…";
  const res = await fetch(`/api/persons/${id}/images`, { method: "POST", body: fd });
  if (res.ok) {
    enrollState.value = "done";
    enrollMsg.value   = "Photo enrolled.";
    load();
  } else {
    const data = await res.json().catch(() => ({}));
    enrollState.value = "error";
    enrollMsg.value   = (data as { detail?: string }).detail ?? "Upload failed.";
  }
  (e.target as HTMLInputElement).value = "";
  uploadingId.value = null;
}

async function toggleBlock(p: Person) {
  await fetch(`/api/persons/${p.person_id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ is_blocked: !p.is_blocked }),
  });
  load();
}

async function deletePerson(id: string) {
  if (!confirm("Delete this person?")) return;
  await fetch(`/api/persons/${id}`, { method: "DELETE" });
  load();
}
</script>

<template>
  <div style="display:flex;flex-direction:column;gap:2.5rem">

    <input ref="uploadInput" type="file" accept="image/*" style="display:none" @change="handleUpload" />

    <div>
      <p class="eyebrow">Access Control</p>
      <div class="eyebrow-bar" />
      <h2 style="font-size:2rem;margin-top:1.25rem">Persons</h2>
      <p style="color:var(--color-muted);margin-top:0.75rem;font-size:0.95rem">
        Enroll known persons so the system can identify and suppress alerts for them.
      </p>
    </div>

    <!-- Add person -->
    <div class="card" style="max-width:480px">
      <p style="font-family:var(--font-mono);font-size:0.72rem;letter-spacing:0.1em;text-transform:uppercase;color:var(--color-muted);margin-bottom:1rem">
        New Person
      </p>
      <div style="display:flex;gap:0.75rem">
        <input
          v-model="newName" type="text" placeholder="Full name"
          @keydown.enter="createPerson"
        />
        <button class="btn-primary" :disabled="creating || !newName.trim()" @click="createPerson">Add</button>
      </div>
    </div>

    <hr class="section-divider" style="margin:0" />

    <p v-if="persons.length === 0" style="color:var(--color-muted);font-size:0.9rem">No persons enrolled yet.</p>

    <div style="display:flex;flex-direction:column;gap:1rem">
      <div
        v-for="p in persons" :key="p.person_id"
        class="card" style="display:flex;align-items:center;gap:1.5rem;flex-wrap:wrap"
      >
        <!-- Info -->
        <div style="flex:1;min-width:180px">
          <div style="font-weight:600;font-size:0.95rem;display:flex;align-items:center;gap:0.6rem">
            {{ p.name }}
            <span v-if="p.is_blocked" class="badge badge-unallowed">blocked</span>
          </div>
          <div style="font-family:var(--font-mono);font-size:0.7rem;color:var(--color-muted);margin-top:0.25rem">
            {{ p.embedding_count }} embedding{{ p.embedding_count !== 1 ? "s" : "" }} · added {{ new Date(p.created_at).toLocaleDateString() }}
          </div>
        </div>

        <!-- Enrollment -->
        <div style="min-width:200px;display:flex;flex-direction:column;gap:0.4rem">
          <div style="display:flex;gap:0.5rem;flex-wrap:wrap">
            <button class="btn-secondary" style="font-size:0.8rem"
              :disabled="enrollId === p.person_id && enrollState === 'waiting'"
              @click="startEnroll(p.person_id)">
              {{ p.embedding_count > 0 ? "Re-enroll" : "Enroll face" }}
            </button>
            <button class="btn-secondary" style="font-size:0.8rem"
              :disabled="enrollId === p.person_id && enrollState === 'waiting'"
              @click="triggerUpload(p.person_id)"
              title="Upload a photo — use this for side-angle cameras">
              + Photo
            </button>
          </div>
          <div v-if="enrollId === p.person_id" style="display:flex;flex-direction:column;gap:0.3rem">
            <span :style="{
              fontSize: '0.8rem',
              fontFamily: 'var(--font-mono)',
              color: enrollState === 'done' ? 'var(--color-success)' : enrollState === 'error' ? 'var(--color-error)' : 'var(--color-muted)'
            }">{{ enrollMsg }}</span>
            <button v-if="enrollState === 'done' || enrollState === 'error'"
              class="btn-secondary" style="font-size:0.75rem;padding:0.3rem 0.75rem" @click="clearEnroll">
              Dismiss
            </button>
          </div>
        </div>

        <!-- Actions -->
        <div style="display:flex;gap:0.6rem">
          <button class="btn-secondary" style="font-size:0.8rem" @click="toggleBlock(p)">
            {{ p.is_blocked ? "Unblock" : "Block" }}
          </button>
          <button class="btn-danger" style="font-size:0.8rem" @click="deletePerson(p.person_id)">Delete</button>
        </div>
      </div>
    </div>

  </div>
</template>
