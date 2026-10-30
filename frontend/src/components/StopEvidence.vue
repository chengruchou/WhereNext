<script lang="ts" setup>
  import { computed } from "vue"
  import { inspector } from "@/inspector"
  import type { EvidenceRecord, SignalName, StageStatus } from "@/types/evidence"

  const props = defineProps<{
    record: EvidenceRecord
    stages: StageStatus[]
  }>()

  // Same colors and order as the paper figures; costs are gray.
  const SIGNALS: { name: SignalName; label: string; color: string }[] = [
    { name: "habit", label: "Your habits", color: "#2a78d6" },
    { name: "semantic_history", label: "Like past visits", color: "#e87ba4" },
    { name: "geo", label: "Close by", color: "#1baf7a" },
    { name: "intent", label: "Close to your request", color: "#eb6834" },
    { name: "novelty", label: "New for you", color: "#eda100" },
    { name: "travel", label: "Travel cost", color: "#898781" },
    { name: "repeat", label: "Repeats a stop type", color: "#52514e" },
  ]

  const STAGE_LABELS: Record<string, string> = {
    sbr: "Sequence model",
    spatial: "Nearby",
    semantic: "Like past visits",
    intent_score: "Request",
    route_plan: "Route",
  }

  const rows = computed(() => {
    const items = SIGNALS.map((s) => ({ ...s, signal: props.record.signals[s.name] }))
      .filter((s) => s.signal && Math.abs(s.signal.contribution) >= 0.005)
      .map((s) => ({ ...s, contribution: s.signal!.contribution }))
    const largest = Math.max(...items.map((s) => Math.abs(s.contribution)), 1e-9)
    return items.map((s) => ({ ...s, width: (Math.abs(s.contribution) / largest) * 100 }))
  })

  const facts = computed(() => {
    const r = props.record
    const lines: string[] = []
    if (r.intent && r.intent.matched_want.length > 0) {
      lines.push(`One of the types you asked for: ${r.intent.matched_want.map((c) => c.trim()).join(", ")}`)
    } else if (r.intent && r.intent.in_range != null) {
      lines.push(
        r.intent.in_range === 0
          ? `Nothing you asked for within ${r.intent.search_radius_km} km of the previous stop`
          : "Not one of the types you asked for",
      )
    }
    const h = r.history
    lines.push(
      h.same_category_visits === 0
        ? `New type for you: none of your last ${h.history_window} visits`
        : `${h.same_category_visits} of your last ${h.history_window} visits were this type`,
    )
    return lines
  })

  const stepStages = computed(() =>
    props.stages
      .filter((s) => s.step === props.record.step && STAGE_LABELS[s.stage])
      .map((s) => ({ ...s, label: STAGE_LABELS[s.stage] })),
  )

  const stageIcon = (status: string) =>
    status === "ran" ? "mdi-check" : status === "skipped" ? "mdi-minus" : "mdi-alert-outline"

  const formatSigned = (value: number) => `${value >= 0 ? "+" : "−"}${Math.abs(value).toFixed(2)}`
</script>

<template>
  <section class="stop-evidence" :aria-label="`Score parts for stop ${record.step}`">
    <!-- Visitors compare the bars; the Inspector adds the numbers behind them. -->
    <div class="stop-evidence__rows">
      <div
        v-for="row in rows"
        :key="row.name"
        class="stop-evidence__row"
        :class="{ 'stop-evidence__row--numbers': inspector }">
        <span class="stop-evidence__label">{{ row.label }}</span>
        <div class="stop-evidence__track">
          <div class="stop-evidence__bar" :style="{ width: `${row.width}%`, background: row.color }" />
        </div>
        <span v-if="inspector" class="stop-evidence__value">{{ formatSigned(row.contribution) }}</span>
      </div>
    </div>
    <div v-if="inspector" class="stop-evidence__total">
      Score {{ record.final_score.toFixed(2) }}, the sum of these parts
    </div>

    <ul class="stop-evidence__facts">
      <li v-for="line in facts" :key="line">{{ line }}</li>
    </ul>

    <div v-if="inspector" class="stop-evidence__stages">
      <v-tooltip v-for="s in stepStages" :key="s.stage" location="top">
        <template #activator="{ props: tip }">
          <v-chip v-bind="tip" size="x-small" variant="text" :prepend-icon="stageIcon(s.status)">
            {{ s.label }}<span v-if="s.latency_ms != null">&nbsp;{{ s.latency_ms.toFixed(0) }} ms</span>
          </v-chip>
        </template>
        <span>{{ s.status }}{{ s.detail ? `: ${s.detail}` : "" }}</span>
      </v-tooltip>
    </div>
  </section>
</template>

<style scoped>
  .stop-evidence {
    padding: 4px 0 2px;
  }

  .stop-evidence__rows {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .stop-evidence__row {
    align-items: center;
    display: grid;
    gap: 8px;
    grid-template-columns: 9.5em minmax(0, 1fr);
  }

  .stop-evidence__row--numbers {
    grid-template-columns: 9.5em minmax(0, 1fr) 3.2em;
  }

  .stop-evidence__label {
    font-size: 0.75rem;
  }

  .stop-evidence__track {
    background: rgba(var(--v-theme-on-surface), 0.06);
    border-radius: 2px;
    height: 6px;
  }

  .stop-evidence__bar {
    border-radius: 2px;
    height: 100%;
  }

  .stop-evidence__value {
    font-size: 0.75rem;
    font-variant-numeric: tabular-nums;
    text-align: right;
  }

  .stop-evidence__total {
    color: rgba(var(--v-theme-on-surface), 0.6);
    font-size: 0.75rem;
    font-variant-numeric: tabular-nums;
    margin-top: 4px;
    text-align: right;
  }

  .stop-evidence__facts {
    color: rgba(var(--v-theme-on-surface), 0.72);
    font-size: 0.75rem;
    line-height: 1.4;
    margin: 6px 0 4px;
    padding-left: 1.1em;
  }

  .stop-evidence__stages {
    display: flex;
    flex-wrap: wrap;
    gap: 2px;
    margin-left: -6px;
  }
</style>
