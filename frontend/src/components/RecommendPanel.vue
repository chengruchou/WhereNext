<script lang="ts" setup>
  import { computed, nextTick, watch } from "vue"
  import type {
    EvidenceRecord,
    PoiFacts,
    RouteEvidence,
    SignalName,
    VerifiedExplanation,
  } from "@/types/evidence"
  import type { GowallaPlace } from "@/types/place"
  import { cleanPhrase, formatKm, haversineKm } from "@/utils/route"
  import StepHeading from "./StepHeading.vue"
  import StopEvidence from "./StopEvidence.vue"

  const props = defineProps<{
    recommendations: GowallaPlace[][]
    isInferring: boolean
    hist: GowallaPlace[] | null
    evidence: RouteEvidence | null
    explanation: VerifiedExplanation | null
    explainModel: string
    explainError: string
    isExplaining: boolean
    openStep: number | null
    hoveredStep: number | null
  }>()

  const emit = defineEmits<{
    (e: "trigger-inference"): void
    (e: "focus-place", payload: { focusPlace: GowallaPlace | null }): void
    (e: "submit-add-history", payload: { passPlace: GowallaPlace | null }): void
    (e: "update:openStep", index: number | null): void
    (e: "hover-step", index: number | null): void
  }>()

  // A first leg longer than this gets a note saying why the route starts far away.
  const FAR_FIRST_LEG_KM = 5

  const TRAVEL_ICONS: Record<string, string> = {
    walk: "mdi-walk",
    drive: "mdi-car",
    transit: "mdi-bus",
  }

  // The one reason shown next to a stop the request did not pick.
  const REASON_LABELS: Partial<Record<SignalName, string>> = {
    habit: "Fits your habits",
    semantic_history: "Like past visits",
    geo: "Close by",
    intent: "Close to your request",
    novelty: "New for you",
  }

  // The open stop is shared with the map, which frames it and shows its other options;
  // clicking a stop's pin opens it here too, so bring it into view.
  const toggleStep = (index: number) => {
    emit("update:openStep", props.openStep === index ? null : index)
  }

  watch(
    () => props.openStep,
    async (index) => {
      if (index == null) return
      await nextTick()
      const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches
      document
        .getElementById(`route-stop-${index}`)
        ?.scrollIntoView({ block: "nearest", behavior: reduced ? "auto" : "smooth" })
    },
  )

  const hasHistory = computed(() => Boolean(props.hist && props.hist.length > 0))
  const hasRoute = computed(() => props.recommendations.length > 0 && props.evidence != null)

  const isMatched = (record: EvidenceRecord) => (record.intent?.matched_want.length ?? 0) > 0

  const fromPoi = (index: number): PoiFacts | null => {
    const evidence = props.evidence
    if (!evidence) return null
    if (index > 0) return evidence.steps[index - 1]?.poi ?? null
    const from = evidence.steps[0]?.travel?.from_raw_poi_id
    return evidence.history.find((h) => h.raw_poi_id === from) ?? evidence.history.at(-1) ?? null
  }

  const stops = computed(() => {
    const evidence = props.evidence
    if (!evidence) return []
    return evidence.steps.map((record, index) => {
      const from = fromPoi(index)
      const round = props.recommendations[index] ?? []
      const alternatives = round.slice(1).map((place) => ({
        place,
        km: from ? haversineKm(from.latitude, from.longitude, place.latitude, place.longitude) : null,
      }))
      return {
        record,
        index,
        place: round[0] ?? null,
        name: (record.poi.category_name ?? "Stop").trim(),
        fromName: index === 0 ? "your last visit" : (from?.category_name ?? "the last stop").trim(),
        matched: isMatched(record),
        reason: isMatched(record) ? "Asked for" : (REASON_LABELS[record.top_signal] ?? ""),
        alternatives,
      }
    })
  })

  const wantText = computed(() => {
    const want = props.evidence?.intent?.want ?? []
    const phrases = [...new Set(want.map((m) => cleanPhrase(m.phrase || m.category_name)))]
    return phrases.join(" or ")
  })

  // Said once at the top of the route, only when the request and the route need squaring.
  const notice = computed<{ type: "info" | "warning"; text: string } | null>(() => {
    const evidence = props.evidence
    if (!evidence?.intent || evidence.intent.want.length === 0 || evidence.steps.length === 0) {
      return null
    }
    const steps = evidence.steps
    const radius = steps[0].intent?.search_radius_km
    const what = `"${wantText.value}"`
    const unmatched = steps.filter((s) => !isMatched(s))
    if (unmatched.length === steps.length) {
      if (steps.every((s) => s.intent?.in_range === 0)) {
        return {
          type: "warning",
          text: `Nothing matching ${what} within ${radius} km of your stops in this data. These stops follow your habits instead.`,
        }
      }
      return {
        type: "info",
        text: `Places matching ${what} are within reach, but your habits ranked higher with these weights.`,
      }
    }
    if (unmatched.length > 0) {
      const names = unmatched.map((s) => s.step)
      const who = names.length === 1 ? `Stop ${names[0]} follows` : `Stops ${names.join(" and ")} follow`
      const why = unmatched.every((s) => s.intent?.in_range === 0)
        ? `: nothing else matching ${what} within ${radius} km`
        : ""
      return { type: "info", text: `${who} your habits${why}.` }
    }
    const first = steps[0].travel
    if (first && first.distance_km > FAR_FIRST_LEG_KM) {
      return {
        type: "info",
        text: `Stop 1 is ${formatKm(first.distance_km)} away. Places you asked for come first, even when others are closer.`,
      }
    }
    return null
  })

  // Checked sentences only; the ones the data does not support are dropped.
  const sentences = computed(() => {
    const explanation = props.explanation
    if (!explanation) return null
    const shown = new Set(
      explanation.verdicts
        .filter((v) => v.verdict !== "unsupported")
        .map((v) => `${v.step ?? "summary"}:${v.index}`),
    )
    const summary = explanation.explanation.summary
      .filter((_, i) => shown.has(`summary:${i}`))
      .map((s) => s.text)
      .join(" ")
    const byStep = new Map<number, string>()
    for (const step of explanation.explanation.steps) {
      const text = step.sentences
        .filter((_, i) => shown.has(`${step.step}:${i}`))
        .map((s) => s.text)
        .join(" ")
      if (text) byStep.set(step.step, text)
    }
    return { summary, byStep }
  })

  const checkLine = computed(() => {
    const explanation = props.explanation
    if (!explanation) return ""
    const count = { supported: 0, unverifiable: 0, unsupported: 0 }
    for (const v of explanation.verdicts) count[v.verdict] += 1
    const total = explanation.verdicts.length
    const noun = total === 1 ? "sentence" : "sentences"
    if (count.supported === total) return `All ${total} ${noun} checked against the data.`
    const parts = [`${count.supported} of ${total} ${noun} checked against the data`]
    if (count.unverifiable > 0) parts.push(`${count.unverifiable} could not be checked`)
    if (count.unsupported > 0) {
      parts.push(`${count.unsupported} removed because the data does not support it`)
    }
    return `${parts.join("; ")}.`
  })

  const alternativesLabel = (count: number) =>
    count === 0 ? "Why this stop" : `Why this stop · ${count} other ${count === 1 ? "option" : "options"}`

  const formatCount = (value: number | null) =>
    value == null ? null : new Intl.NumberFormat("en-US").format(value)
</script>

<template>
  <section class="route-panel">
    <header class="route-panel__header">
      <StepHeading :step="3" title="Your route" class="route-panel__title" />
      <v-btn
        v-if="hasRoute || isInferring"
        size="small"
        variant="text"
        prepend-icon="mdi-refresh"
        class="route-panel__again"
        :loading="isInferring"
        :disabled="isInferring || !hasHistory"
        @click="emit('trigger-inference')">
        Plan again
      </v-btn>
    </header>

    <div class="route-panel__body">
      <div v-if="isInferring && !hasRoute" class="route-panel__loading" aria-busy="true">
        <v-skeleton-loader v-for="n in 3" :key="n" type="list-item-avatar-two-line" />
      </div>

      <div v-else-if="!hasRoute" class="route-panel__empty">
        <template v-if="hasHistory">
          <p class="route-panel__empty-text">
            Describe what you want above, or plan the next stops from this user's visits alone.
          </p>
          <v-btn color="primary" variant="flat" block @click="emit('trigger-inference')">
            Plan route
          </v-btn>
        </template>
        <p v-else class="route-panel__empty-text">
          Load a traveler above. The route starts from their last visit.
        </p>
      </div>

      <template v-else-if="evidence">
        <v-alert
          v-if="notice"
          :type="notice.type"
          variant="tonal"
          density="compact"
          class="route-panel__notice"
          :text="notice.text" />

        <p v-if="sentences?.summary" class="route-panel__summary">{{ sentences.summary }}</p>
        <v-skeleton-loader v-else-if="isExplaining" type="text" class="route-panel__summary-skeleton" />

        <ol class="route-panel__timeline" :class="{ 'route-panel__timeline--busy': isInferring }">
          <li
            v-for="stop in stops"
            :id="`route-stop-${stop.index}`"
            :key="stop.record.step"
            class="route-panel__stop"
            :class="{ 'route-panel__stop--active': hoveredStep === stop.index || openStep === stop.index }"
            @mouseenter="emit('hover-step', stop.index)"
            @mouseleave="emit('hover-step', null)"
            @focusin="emit('hover-step', stop.index)"
            @focusout="emit('hover-step', null)">
            <div class="route-panel__leg">
              <v-icon
                :icon="TRAVEL_ICONS[stop.record.travel?.mode ?? 'drive'] ?? 'mdi-map-marker-path'"
                size="14" />
              <span v-if="stop.record.travel">
                {{ formatKm(stop.record.travel.distance_km) }} from {{ stop.fromName }}
              </span>
            </div>

            <div class="route-panel__stop-main">
              <span
                class="route-panel__badge"
                aria-hidden="true">
                {{ stop.record.step }}
              </span>
              <div class="route-panel__stop-text">
                <div class="route-panel__stop-head">
                  <button
                    type="button"
                    class="route-panel__stop-name"
                    :aria-label="`Show ${stop.name} on the map`"
                    @click="emit('focus-place', { focusPlace: stop.place })">
                    {{ stop.name }}
                  </button>
                  <v-btn
                    icon="mdi-plus"
                    size="x-small"
                    variant="text"
                    :aria-label="`Add ${stop.name} to history`"
                    @click="emit('submit-add-history', { passPlace: stop.place })" />
                </div>
                <div class="route-panel__meta">
                  <span v-if="stop.reason" :class="{ 'route-panel__asked': stop.matched }">
                    {{ stop.reason }}
                  </span>
                  <span v-if="formatCount(stop.record.poi.checkins_count)">
                    {{ formatCount(stop.record.poi.checkins_count) }} check-ins
                  </span>
                </div>
                <p v-if="sentences?.byStep.get(stop.record.step)" class="route-panel__sentence">
                  {{ sentences.byStep.get(stop.record.step) }}
                </p>
                <v-skeleton-loader v-else-if="isExplaining" type="text" class="route-panel__sentence-skeleton" />

                <button
                  type="button"
                  class="route-panel__why"
                  :aria-expanded="openStep === stop.index"
                  @click="toggleStep(stop.index)">
                  {{ alternativesLabel(stop.alternatives.length) }}
                  <v-icon :icon="openStep === stop.index ? 'mdi-chevron-up' : 'mdi-chevron-down'" size="14" />
                </button>

                <div v-if="openStep === stop.index" class="route-panel__detail">
                  <StopEvidence :record="stop.record" :stages="evidence.stages" />
                  <ul v-if="stop.alternatives.length > 0" class="route-panel__alts">
                    <li v-for="alt in stop.alternatives" :key="alt.place.raw_poi_id" class="route-panel__alt">
                      <button
                        type="button"
                        class="route-panel__alt-name"
                        :aria-label="`Show ${alt.place.category_name ?? 'place'} on the map`"
                        @click="emit('focus-place', { focusPlace: alt.place })">
                        {{ (alt.place.category_name ?? "Place").trim() }}
                      </button>
                      <span v-if="alt.km != null" class="route-panel__alt-km">{{ formatKm(alt.km) }}</span>
                      <v-btn
                        icon="mdi-plus"
                        size="x-small"
                        variant="text"
                        :aria-label="`Add ${alt.place.category_name ?? 'place'} to history`"
                        @click="emit('submit-add-history', { passPlace: alt.place })" />
                    </li>
                  </ul>
                </div>
              </div>
            </div>
          </li>
        </ol>

        <footer v-if="checkLine || explainError || isExplaining" class="route-panel__footer">
          <span v-if="checkLine">{{ checkLine }} Written by {{ explainModel }}.</span>
          <span v-else-if="explainError">{{ explainError }}</span>
          <span v-else-if="isExplaining">Writing the explanation…</span>
        </footer>
      </template>
    </div>
  </section>
</template>

<style scoped>
  .route-panel__header {
    align-items: center;
    display: flex;
    justify-content: space-between;
    margin-bottom: 8px;
  }

  .route-panel__title {
    margin: 0;
  }

  .route-panel__again {
    letter-spacing: 0;
    text-transform: none;
  }

  .route-panel__empty {
    border: 1px dashed rgba(var(--v-border-color), 0.3);
    border-radius: 8px;
    padding: 16px;
  }

  .route-panel__empty-text {
    color: rgba(var(--v-theme-on-surface), 0.72);
    font-size: 0.82rem;
    line-height: 1.45;
    margin: 0 0 12px;
  }

  .route-panel__empty-text:last-child {
    margin-bottom: 0;
  }

  .route-panel__notice {
    flex: 0 0 auto;
    font-size: 0.78rem;
    margin-bottom: 10px;
  }

  .route-panel__summary {
    font-size: 0.86rem;
    line-height: 1.5;
    margin: 0 0 12px;
  }

  .route-panel__summary-skeleton,
  .route-panel__sentence-skeleton {
    background: transparent;
    margin: 0 0 8px -16px;
  }

  .route-panel__timeline {
    list-style: none;
    margin: 0;
    padding: 0;
    transition: opacity 0.2s ease;
  }

  .route-panel__timeline--busy {
    opacity: 0.5;
  }

  .route-panel__stop {
    position: relative;
  }

  /* The line joining the stops runs behind the badges. */
  .route-panel__stop::before {
    background: rgba(var(--v-border-color), 0.35);
    bottom: 0;
    content: "";
    left: 11px;
    position: absolute;
    top: 0;
    width: 2px;
  }

  .route-panel__stop:last-child::before {
    bottom: auto;
    height: 34px;
  }

  .route-panel__leg {
    align-items: center;
    color: rgba(var(--v-theme-on-surface), 0.64);
    display: flex;
    font-size: 0.75rem;
    font-variant-numeric: tabular-nums;
    gap: 6px;
    padding: 2px 0 6px 32px;
    position: relative;
  }

  .route-panel__stop-main {
    display: flex;
    gap: 10px;
    padding-bottom: 14px;
  }

  /* Same numbers and color as the stop pins on the map. */
  .route-panel__badge {
    align-items: center;
    background: rgb(var(--v-theme-primary));
    border-radius: 50%;
    color: rgb(var(--v-theme-on-primary));
    display: flex;
    flex-shrink: 0;
    font-size: 0.75rem;
    font-weight: 700;
    height: 24px;
    justify-content: center;
    position: relative;
    transition: box-shadow 0.15s ease;
    width: 24px;
  }

  .route-panel__stop--active .route-panel__badge {
    box-shadow: 0 0 0 4px rgba(var(--v-theme-primary), 0.25);
  }

  .route-panel__stop--active .route-panel__stop-name {
    color: rgb(var(--v-theme-primary));
  }

  .route-panel__stop-text {
    flex: 1 1 auto;
    min-width: 0;
  }

  .route-panel__stop-head {
    align-items: center;
    display: flex;
    gap: 4px;
    justify-content: space-between;
    margin-top: 1px;
  }

  .route-panel__stop-name,
  .route-panel__alt-name {
    background: none;
    border: 0;
    border-radius: 4px;
    color: rgb(var(--v-theme-on-surface));
    cursor: pointer;
    min-width: 0;
    padding: 0;
    text-align: left;
  }

  .route-panel__stop-name {
    font-size: 0.92rem;
    font-weight: 700;
    line-height: 1.3;
  }

  .route-panel__stop-name:hover,
  .route-panel__alt-name:hover {
    text-decoration: underline;
  }

  .route-panel__stop-name:focus-visible,
  .route-panel__alt-name:focus-visible,
  .route-panel__why:focus-visible {
    outline: 2px solid rgb(var(--v-theme-primary));
    outline-offset: 2px;
  }

  .route-panel__meta {
    color: rgba(var(--v-theme-on-surface), 0.64);
    display: flex;
    flex-wrap: wrap;
    font-size: 0.75rem;
    gap: 4px 12px;
    margin-top: 1px;
  }

  .route-panel__asked {
    color: rgb(var(--v-theme-primary));
    font-weight: 700;
  }

  .route-panel__sentence {
    font-size: 0.82rem;
    line-height: 1.45;
    margin: 6px 0 0;
  }

  .route-panel__why {
    align-items: center;
    background: none;
    border: 0;
    border-radius: 4px;
    color: rgba(var(--v-theme-on-surface), 0.64);
    cursor: pointer;
    display: inline-flex;
    font-size: 0.75rem;
    gap: 2px;
    margin-top: 6px;
    padding: 2px 0;
  }

  .route-panel__why:hover {
    color: rgb(var(--v-theme-on-surface));
  }

  .route-panel__detail {
    border-top: 1px solid rgba(var(--v-border-color), 0.18);
    margin-top: 6px;
    padding-top: 6px;
  }

  .route-panel__alts {
    border-top: 1px solid rgba(var(--v-border-color), 0.18);
    list-style: none;
    margin: 6px 0 0;
    padding: 4px 0 0;
  }

  .route-panel__alt {
    align-items: center;
    display: grid;
    font-size: 0.78rem;
    gap: 8px;
    grid-template-columns: minmax(0, 1fr) auto auto;
  }

  .route-panel__alt-name {
    font-size: 0.78rem;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .route-panel__alt-km {
    color: rgba(var(--v-theme-on-surface), 0.64);
    font-variant-numeric: tabular-nums;
  }

  .route-panel__footer {
    border-top: 1px solid rgba(var(--v-border-color), 0.18);
    color: rgba(var(--v-theme-on-surface), 0.6);
    font-size: 0.75rem;
    line-height: 1.4;
    padding-top: 8px;
  }

  @media (prefers-reduced-motion: reduce) {
    .route-panel__timeline,
    .route-panel__badge {
      transition: none;
    }
  }
</style>
