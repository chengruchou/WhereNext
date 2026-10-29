<script lang="ts" setup>
  import { computed, ref } from "vue"
  import type { DemoTraveler } from "@/demo"
  import type { GowallaPlace, UserHistory } from "@/types/place"
  import HistoryList from "./HistoryList.vue"
  import StepHeading from "./StepHeading.vue"
  import UserLogin from "./UserLogin.vue"

  const props = defineProps<{
    userId: number | null
    userHistory: UserHistory[]
    demoTravelers: DemoTraveler[]
    activeDemo: DemoTraveler | null
    loadingDemo: string | null
  }>()

  const emit = defineEmits<{
    (e: "submit-user-id", payload: { passUserId: number | null }): void
    (e: "load-demo", traveler: DemoTraveler): void
    (e: "delete-all"): void
    (e: "delete-one", payload: { delId: number }): void
    (e: "focus-place", payload: { focusPlace: GowallaPlace | null }): void
  }>()

  // The visits fold into one line, so the request and the route stay in view.
  const showVisits = ref(false)

  const summary = computed(() => {
    const visits = props.userHistory
    const who = props.activeDemo ? `${props.activeDemo.label}: ` : ""
    if (visits.length === 0) return `${who}no visits yet`
    const last = visits.at(-1)?.poi_detail?.category_name?.trim() || "unknown place"
    return `${who}${visits.length} ${visits.length === 1 ? "visit" : "visits"}, last at ${last}`
  })
</script>

<template>
  <section class="traveler-panel">
    <StepHeading :step="1" title="Traveler" />
    <UserLogin :current-id="userId" @submit-user-id="emit('submit-user-id', $event)" />

    <div v-if="userId == null && demoTravelers.length > 0" class="traveler-panel__demos">
      <span class="traveler-panel__demos-label">Or start from a demo traveler</span>
      <button
        v-for="t in demoTravelers"
        :key="t.key"
        type="button"
        class="traveler-panel__demo"
        :disabled="loadingDemo != null"
        @click="emit('load-demo', t)">
        <span class="traveler-panel__demo-name">{{ t.label }}</span>
        <span class="traveler-panel__demo-text">{{ t.description }}</span>
        <v-progress-circular
          v-if="loadingDemo === t.key"
          indeterminate
          size="16"
          width="2"
          class="traveler-panel__demo-busy" />
      </button>
    </div>

    <template v-if="userId != null">
      <button
        type="button"
        class="traveler-panel__summary"
        :aria-expanded="showVisits"
        @click="showVisits = !showVisits">
        <span>{{ summary }}</span>
        <span class="traveler-panel__toggle">
          {{ showVisits ? "Hide" : "Show" }}
          <v-icon :icon="showVisits ? 'mdi-chevron-up' : 'mdi-chevron-down'" size="16" />
        </span>
      </button>

      <HistoryList
        v-if="showVisits"
        :user-history="userHistory"
        @delete-all="emit('delete-all')"
        @delete-one="emit('delete-one', $event)"
        @focus-place="emit('focus-place', $event)" />
    </template>
  </section>
</template>

<style scoped>
  .traveler-panel {
    border-bottom: 1px solid rgba(var(--v-border-color), 0.18);
    margin-bottom: 14px;
    padding-bottom: 14px;
  }

  .traveler-panel__demos {
    display: flex;
    flex-direction: column;
    gap: 6px;
    margin-top: 10px;
  }

  .traveler-panel__demos-label {
    color: rgba(var(--v-theme-on-surface), 0.72);
    font-size: 0.8rem;
  }

  .traveler-panel__demo {
    background: none;
    border: 1px solid rgba(var(--v-border-color), 0.28);
    border-radius: 8px;
    color: inherit;
    cursor: pointer;
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    padding: 8px 10px;
    text-align: left;
  }

  .traveler-panel__demo:hover:not(:disabled) {
    border-color: rgb(var(--v-theme-primary));
  }

  .traveler-panel__demo:focus-visible {
    outline: 2px solid rgb(var(--v-theme-primary));
    outline-offset: 2px;
  }

  .traveler-panel__demo:disabled {
    cursor: progress;
    opacity: 0.7;
  }

  .traveler-panel__demo-name {
    font-size: 0.85rem;
    font-weight: 700;
    grid-column: 1;
  }

  .traveler-panel__demo-text {
    color: rgba(var(--v-theme-on-surface), 0.64);
    font-size: 0.78rem;
    grid-column: 1;
  }

  .traveler-panel__demo-busy {
    align-self: center;
    grid-column: 2;
    grid-row: 1 / span 2;
  }

  .traveler-panel__summary {
    align-items: center;
    background: none;
    border: 0;
    border-radius: 4px;
    color: rgba(var(--v-theme-on-surface), 0.8);
    cursor: pointer;
    display: flex;
    font-size: 0.82rem;
    gap: 8px;
    justify-content: space-between;
    margin: 8px 0 6px;
    padding: 2px 0;
    text-align: left;
    width: 100%;
  }

  .traveler-panel__summary:focus-visible {
    outline: 2px solid rgb(var(--v-theme-primary));
    outline-offset: 2px;
  }

  .traveler-panel__toggle {
    align-items: center;
    color: rgb(var(--v-theme-primary));
    display: inline-flex;
    flex-shrink: 0;
    font-size: 0.78rem;
  }
</style>
