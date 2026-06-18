<script setup lang="ts">
const LABELS: Record<string, string> = {
  unknown:    "unknown",
  known:      "authorized",
  unallowed:  "blocked",
  no_face:    "no face",
  false_alarm: "false alarm",
  online:     "online",
  offline:    "offline",
  armed:      "armed",
  disarmed:   "disarmed",
};

const props = defineProps<{ value: string }>();
const key = () => props.value?.toLowerCase() ?? "unknown";
</script>

<template>
  <span :class="`badge badge-${key()}`">{{ LABELS[key()] ?? key() }}</span>
</template>
