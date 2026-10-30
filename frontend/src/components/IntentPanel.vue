<script lang="ts" setup>
  import { computed, ref } from "vue"
  import type { CategoryMatch, Intent, SteeringControls } from "@/types/intent"
  import { inspector } from "@/inspector"
  import { cleanPhrase } from "@/utils/route"
  import StepHeading from "./StepHeading.vue"

  const props = defineProps<{
    intent: Intent | null
    controls: SteeringControls | null
    isParsing: boolean
    parseError: string
    examples: string[]
  }>()

  const emit = defineEmits<{
    (e: "submit-request", payload: { query: string }): void
    (e: "clear-request"): void
    (e: "edit-intent", payload: { intent: Intent }): void
  }>()

  const query = ref("")
  const openGroup = ref<string | null>(null)
  const showReading = ref(false)

  const parseRequest = () => {
    const text = query.value.trim()
    if (text && !props.isParsing) emit("submit-request", { query: text })
  }

  const useExample = (text: string) => {
    query.value = text
    parseRequest()
  }

  const clearRequest = () => {
    query.value = ""
    openGroup.value = null
    emit("clear-request")
  }

  // Removing a type edits the intent; the server re-derives the weights when the route runs.
  const removeMatch = (list: "want" | "avoid", match: CategoryMatch) => {
    if (!props.intent) return
    const updated: Intent = { ...props.intent, source: "user_edit" }
    updated[list] = props.intent[list].filter((m) => m.category_name !== match.category_name)
    emit("edit-intent", { intent: updated })
  }

  // One chip per phrase the user wrote; the place types it resolved to open under it.
  const groups = computed(() => {
    const intent = props.intent
    if (!intent) return []
    const result: { key: string; list: "want" | "avoid"; phrase: string; matches: CategoryMatch[] }[] =
      []
    for (const list of ["want", "avoid"] as const) {
      const byPhrase = new Map<string, CategoryMatch[]>()
      for (const m of intent[list]) {
        const phrase = m.phrase.trim() || m.category_name.trim()
        byPhrase.set(phrase, [...(byPhrase.get(phrase) ?? []), m])
      }
      for (const [phrase, matches] of byPhrase) {
        result.push({ key: `${list}:${phrase}`, list, phrase, matches })
      }
    }
    return result
  })

  const groupLabel = (g: { list: string; phrase: string; matches: CategoryMatch[] }) => {
    const phrase = cleanPhrase(g.phrase)
    const negated = /^(no|nothing|not|without)\b/i.test(phrase)
    const head = g.list === "avoid" && !negated ? `no ${phrase}` : phrase
    if (g.matches.length > 1) return `${head} · ${g.matches.length} types`
    const only = g.matches[0].category_name.trim()
    return only.toLowerCase() === phrase.toLowerCase() ? head : `${head} · ${only}`
  }

  const openMatches = computed(() => groups.value.find((g) => g.key === openGroup.value) ?? null)

  const toggleGroup = (key: string) => {
    openGroup.value = openGroup.value === key ? null : key
  }

  const TRAVEL_ICONS: Record<string, string> = {
    walk: "mdi-walk",
    drive: "mdi-car",
    transit: "mdi-bus",
  }

  const constraints = computed(() => {
    const intent = props.intent
    if (!intent) return []
    const items = [
      { icon: TRAVEL_ICONS[intent.travel_mode] ?? "mdi-map-marker-path", text: intent.travel_mode },
      { icon: "mdi-map-marker-multiple-outline", text: `${intent.num_stops} stops` },
    ]
    if (intent.max_hop_km != null) {
      items.push({ icon: "mdi-ruler", text: `up to ${intent.max_hop_km} km a leg` })
    }
    if (intent.time_budget_min != null) {
      items.push({ icon: "mdi-timer-outline", text: `${intent.time_budget_min} min` })
    }
    return items
  })

  // What the weights mean, in one sentence; the numbers are in the Inspector view.
  const weightSentence = computed(() => {
    const intent = props.intent
    if (!intent) return ""
    const lead =
      intent.want.length > 0 && (props.controls?.habit_intent ?? 0) > 0
        ? "Your request comes first. Your habits break ties."
        : "No place type asked for, so your habits lead."
    if (intent.explore === "new") return `${lead} Places new to you get a lift.`
    if (intent.explore === "familiar") return `${lead} Familiar kinds of places are kept.`
    return lead
  })

  const parserLabel = computed(() => {
    const intent = props.intent
    if (!intent) return ""
    if (intent.source === "user_edit") return "Edited by you."
    if (!intent.parser) return ""
    return intent.parser.fallback
      ? "Read by the offline keyword parser."
      : `Read by ${intent.parser.model}.`
  })

  const percent = (value: number | undefined) => `${Math.round((value ?? 0) * 100)}%`
</script>

<template>
  <section class="intent-panel">
    <StepHeading :step="2" title="What are you looking for?" label-for="intent-query" />
    <v-text-field
      id="intent-query"
      v-model="query"
      density="comfortable"
      variant="outlined"
      hide-details="auto"
      placeholder="e.g. museums, nothing with coffee"
      :error-messages="parseError || undefined"
      :loading="isParsing"
      @keyup.enter="parseRequest">
      <template #append-inner>
        <v-btn
          icon="mdi-arrow-right"
          size="small"
          variant="flat"
          color="primary"
          aria-label="Plan a route for this request"
          :disabled="!query.trim() || isParsing"
          @click="parseRequest" />
      </template>
    </v-text-field>

    <div v-if="!intent && examples.length > 0" class="intent-panel__examples">
      <span class="intent-panel__examples-label">Try</span>
      <v-chip
        v-for="text in examples"
        :key="text"
        size="small"
        variant="outlined"
        :disabled="isParsing"
        @click="useExample(text)">
        {{ text }}
      </v-chip>
    </div>

    <template v-if="intent">
      <div class="intent-panel__chips">
        <v-chip
          v-for="g in groups"
          :key="g.key"
          size="small"
          :color="g.list === 'want' ? 'primary' : undefined"
          :variant="g.list === 'want' ? 'tonal' : 'outlined'"
          :prepend-icon="g.list === 'avoid' ? 'mdi-cancel' : undefined"
          :append-icon="openGroup === g.key ? 'mdi-chevron-up' : 'mdi-chevron-down'"
          :aria-expanded="openGroup === g.key"
          @click="toggleGroup(g.key)">
          {{ groupLabel(g) }}
        </v-chip>
        <v-chip
          v-for="c in constraints"
          :key="c.text"
          size="small"
          variant="text"
          :prepend-icon="c.icon"
          class="intent-panel__constraint">
          {{ c.text }}
        </v-chip>
        <v-btn
          size="small"
          variant="text"
          class="intent-panel__clear"
          aria-label="Clear the request"
          @click="clearRequest">
          Clear
        </v-btn>
      </div>

      <div v-if="openMatches" class="intent-panel__types">
        <span class="intent-panel__types-hint">
          Place types for "{{ openMatches.phrase }}". Remove any that don't fit.
        </span>
        <div class="d-flex flex-wrap ga-1">
          <v-chip
            v-for="m in openMatches.matches"
            :key="m.category_name"
            size="x-small"
            variant="outlined"
            closable
            :close-label="`Remove ${m.category_name.trim()}`"
            @click:close="removeMatch(openMatches.list, m)">
            {{ m.category_name.trim() }}
          </v-chip>
        </div>
      </div>

      <p class="intent-panel__sentence">{{ weightSentence }}</p>

      <p v-if="intent.unresolved.length > 0" class="intent-panel__note">
        No place type in the data for: {{ intent.unresolved.join(", ") }}.
      </p>
      <p v-if="intent.unsupported.length > 0" class="intent-panel__note">
        Not in the data, so not used: {{ intent.unsupported.join(", ") }}.
      </p>

      <button
        v-if="inspector"
        type="button"
        class="intent-panel__reading-toggle"
        :aria-expanded="showReading"
        @click="showReading = !showReading">
        How this was read
        <v-icon :icon="showReading ? 'mdi-chevron-up' : 'mdi-chevron-down'" size="14" />
      </button>
      <dl v-if="inspector && showReading" class="intent-panel__reading">
        <dt>Weight on your request</dt>
        <dd>{{ percent(controls?.habit_intent) }}</dd>
        <dt>Weight on places new to you</dt>
        <dd>{{ percent(controls?.explore) }}</dd>
        <dt>Strength</dt>
        <dd>{{ intent.strength }}</dd>
        <dd class="intent-panel__reading-source">
          Set from your wording, not adjustable. {{ parserLabel }}
        </dd>
      </dl>
    </template>
  </section>
</template>

<style scoped>
  .intent-panel {
    border-bottom: 1px solid rgba(var(--v-border-color), 0.18);
    flex-shrink: 0;
    margin-bottom: 14px;
    padding-bottom: 14px;
  }

  .intent-panel__chips {
    align-items: center;
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin-top: 10px;
  }

  .intent-panel__constraint {
    color: rgba(var(--v-theme-on-surface), 0.72);
    padding-inline: 4px;
  }

  .intent-panel__clear {
    letter-spacing: 0;
    margin-left: auto;
    text-transform: none;
  }

  .intent-panel__types {
    border-left: 2px solid rgba(var(--v-theme-primary), 0.5);
    margin-top: 8px;
    padding: 2px 0 2px 10px;
  }

  .intent-panel__types-hint {
    color: rgba(var(--v-theme-on-surface), 0.68);
    display: block;
    font-size: 0.75rem;
    margin-bottom: 6px;
  }

  .intent-panel__sentence {
    font-size: 0.82rem;
    line-height: 1.45;
    margin: 10px 0 0;
  }

  .intent-panel__note {
    color: rgba(var(--v-theme-on-surface), 0.72);
    font-size: 0.76rem;
    line-height: 1.4;
    margin: 4px 0 0;
  }

  .intent-panel__examples {
    align-items: center;
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin-top: 10px;
  }

  .intent-panel__examples-label {
    color: rgba(var(--v-theme-on-surface), 0.64);
    font-size: 0.78rem;
  }

  .intent-panel__reading-toggle {
    align-items: center;
    background: none;
    border: 0;
    border-radius: 4px;
    color: rgba(var(--v-theme-on-surface), 0.68);
    cursor: pointer;
    display: inline-flex;
    font-size: 0.75rem;
    gap: 2px;
    margin-top: 6px;
    padding: 2px 0;
  }

  .intent-panel__reading-toggle:hover {
    color: rgb(var(--v-theme-on-surface));
  }

  .intent-panel__reading-toggle:focus-visible {
    outline: 2px solid rgb(var(--v-theme-primary));
    outline-offset: 2px;
  }

  .intent-panel__reading {
    display: grid;
    font-size: 0.75rem;
    gap: 2px 12px;
    grid-template-columns: 1fr auto;
    margin: 6px 0 0;
  }

  .intent-panel__reading dt {
    color: rgba(var(--v-theme-on-surface), 0.72);
  }

  .intent-panel__reading dd {
    font-variant-numeric: tabular-nums;
    font-weight: 700;
    margin: 0;
    text-align: right;
  }

  .intent-panel__reading .intent-panel__reading-source {
    color: rgba(var(--v-theme-on-surface), 0.6);
    font-weight: 400;
    grid-column: 1 / -1;
    margin-top: 4px;
    text-align: left;
  }
</style>
