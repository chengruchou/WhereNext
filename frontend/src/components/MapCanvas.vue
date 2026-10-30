<script lang="ts" setup>
  import { ref, watch, computed } from "vue"
  import type { GowallaPlace } from "@/types/place"
  import { GoogleMap, AdvancedMarker, InfoWindow } from "vue3-google-map"
  import { palette } from "@/styles/palette"
  import DrawRoute from "./DrawRoute.vue"
  import PlaceCard from "./PlaceCard.vue"

  // Visits are neutral, search results are outlined, and route stops carry the accent,
  // the same blue as the stop badges in the route panel.
  const PINS = {
    visit: { background: palette.neutral, borderColor: palette.neutralStrong, glyphColor: "white" },
    search: { background: "white", borderColor: palette.neutralStrong, glyphColor: palette.neutralStrong },
    stop: { background: palette.accent, borderColor: palette.accentStrong, glyphColor: "white" },
    option: { background: "white", borderColor: palette.accent, glyphColor: palette.accent },
  }

  type LayerKey = "hist" | "search" | "rec"

  const apiKey = import.meta.env.VITE_GOOGLE_API_KEY
  // Pins need a vector map ID from the same Google Cloud project as the key.
  const mapId = import.meta.env.VITE_GOOGLE_MAP_ID || "506622965fe133bac9a880a1"
  const ROUTE_MODES: Record<string, string> = { walk: "WALK", drive: "DRIVE", transit: "TRANSIT" }

  const props = defineProps<{
    showSearch: GowallaPlace[]
    showRecommend: GowallaPlace[][]
    userHist: GowallaPlace[]
    focusedPlace: GowallaPlace | null
    layers: Record<LayerKey, boolean>
    openStep: number | null
    hoveredStep: number | null
    travelMode: string
  }>()
  const emit = defineEmits<{
    (e: "submit-add-history", payload: { passPlace: GowallaPlace | null }): void
    (e: "toggle-layer", key: LayerKey): void
    (e: "select-step", index: number): void
  }>()

  const center = ref({ lat: 39.0528237667, lng: -94.59031105 })
  const mapRef = ref<any>(null)

  const showPoint = ref<GowallaPlace | null>(null)
  const showPointIndex = ref(0)
  const showPointContext = ref<"search" | "recommendation" | "history">("search")
  const showAdd = ref(true)

  const openInfo = (
    place: GowallaPlace,
    index: number,
    context: "search" | "recommendation" | "history",
  ) => {
    showPoint.value = place
    showPointIndex.value = index
    showPointContext.value = context
    showAdd.value = context !== "history"
  }

  const lastVisit = computed(() => props.userHist.at(-1) ?? null)
  const stops = computed(() =>
    props.showRecommend.map((round) => round?.[0]).filter((p): p is GowallaPlace => Boolean(p)),
  )

  // One leg per stop, from the last visit through the route in order.
  const legs = computed(() => {
    const legs: GowallaPlace[][] = []
    let previous = lastVisit.value
    for (const stop of stops.value) {
      if (previous) legs.push([previous, stop])
      previous = stop
    }
    return legs
  })

  // The other candidates of the stop whose details are open in the route panel.
  const options = computed(() =>
    props.openStep == null ? [] : (props.showRecommend[props.openStep] ?? []).slice(1),
  )

  const isActive = (index: number) => props.hoveredStep === index || props.openStep === index

  const fitTo = (places: (GowallaPlace | null)[]) => {
    const points = places.filter(
      (p): p is GowallaPlace => p != null && p.latitude != null && p.longitude != null,
    )
    // The map may still be loading right after a change; give it a moment.
    setTimeout(() => {
      const map = mapRef.value?.map
      if (!points.length || !map) return
      if (points.length === 1) {
        center.value = { lat: points[0].latitude, lng: points[0].longitude }
        map.panTo(center.value)
        map.setZoom(15)
        return
      }
      map.fitBounds(
        {
          south: Math.min(...points.map((p) => p.latitude)),
          north: Math.max(...points.map((p) => p.latitude)),
          west: Math.min(...points.map((p) => p.longitude)),
          east: Math.max(...points.map((p) => p.longitude)),
        },
        64,
      )
    }, 100)
  }

  const fitRoute = () => fitTo([lastVisit.value, ...stops.value])

  // The map frames whatever changed last: a new route, an opened stop, a search, a traveler.
  watch(() => props.showRecommend, () => stops.value.length > 0 && fitRoute())

  watch(
    () => props.openStep,
    (step) => {
      if (step == null) {
        if (stops.value.length > 0) fitRoute()
        return
      }
      const from = step === 0 ? lastVisit.value : stops.value[step - 1]
      fitTo([from, stops.value[step], ...options.value])
    },
  )

  watch(
    () => props.showSearch,
    (results) => results.length > 0 && fitTo(results),
  )

  watch(
    () => props.userHist,
    (visits) => stops.value.length === 0 && fitTo(visits),
    { immediate: true },
  )

  watch(
    () => props.focusedPlace,
    (place) => {
      if (place && mapRef.value?.map) {
        center.value = { lat: place.latitude, lng: place.longitude }
        mapRef.value.map.panTo(center.value)
        mapRef.value.map.setZoom(15)
      }
    },
  )

  const legend = computed(() => {
    const items: { key: LayerKey; label: string; swatch: Record<string, string> }[] = [
      { key: "hist", label: "Visits", swatch: { background: palette.neutral } },
      { key: "rec", label: "Route", swatch: { background: palette.accent } },
    ]
    if (props.showSearch.length > 0) {
      items.push({
        key: "search",
        label: "Search results",
        swatch: { background: "white", border: `2px solid ${palette.neutralStrong}` },
      })
    }
    return items
  })
</script>

<template>
  <div class="map-canvas">
    <GoogleMap
      ref="mapRef"
      :api-key="apiKey"
      :map-id="mapId"
      style="width: 100%; height: 100%"
      :center="center"
      :zoom="15"
      :disable-default-ui="true"
      @click="showPoint = null">
      <template v-if="props.layers.hist">
        <DrawRoute :points="props.userHist" :type="'hist'" />
        <AdvancedMarker
          v-for="(e, index) in props.userHist"
          :key="'visit-' + e.raw_poi_id + '-' + index"
          :options="{
            position: { lat: e.latitude, lng: e.longitude },
            gmpClickable: true,
            title: `Visit ${index + 1}: ${e.category_name}`,
          }"
          :pinOptions="{ ...PINS.visit, glyphText: String(index + 1), scale: 0.8 }"
          @click="openInfo(e, index, 'history')" />
      </template>

      <template v-if="props.layers.search">
        <AdvancedMarker
          v-for="(e, index) in props.showSearch"
          :key="'search-' + e.raw_poi_id"
          :options="{
            position: { lat: e.latitude, lng: e.longitude },
            gmpClickable: true,
            title: `Search result: ${e.category_name}`,
          }"
          :pinOptions="{ ...PINS.search, scale: 0.7 }"
          @click="openInfo(e, index, 'search')" />
      </template>

      <template v-if="props.layers.rec">
        <DrawRoute
          v-for="(leg, index) in legs"
          :key="'leg-' + index + '-' + leg[1].raw_poi_id"
          :points="leg"
          :type="'rec'"
          :mode="ROUTE_MODES[props.travelMode] ?? 'DRIVE'"
          :highlighted="isActive(index)" />

        <AdvancedMarker
          v-for="(e, index) in options"
          :key="'option-' + e.raw_poi_id"
          :options="{
            position: { lat: e.latitude, lng: e.longitude },
            gmpClickable: true,
            title: `Other option for stop ${(props.openStep ?? 0) + 1}: ${e.category_name}`,
            zIndex: 5,
          }"
          :pinOptions="{ ...PINS.option, glyphText: '', scale: 0.7 }"
          @click="openInfo(e, index + 1, 'recommendation')" />

        <!-- Recreated when its state changes, so the pin's size and order always match. -->
        <AdvancedMarker
          v-for="(e, index) in stops"
          :key="'stop-' + index + '-' + e.raw_poi_id + (isActive(index) ? '-active' : '')"
          :options="{
            position: { lat: e.latitude, lng: e.longitude },
            gmpClickable: true,
            title: `Stop ${index + 1}: ${e.category_name}`,
            zIndex: isActive(index) ? 100 : 10 + index,
          }"
          :pinOptions="{ ...PINS.stop, glyphText: String(index + 1), scale: isActive(index) ? 1.3 : 1 }"
          @click="emit('select-step', index)" />
      </template>

      <InfoWindow
        v-if="showPoint"
        :options="{
          position: { lat: showPoint.latitude, lng: showPoint.longitude },
          headerDisabled: true,
        }">
        <div class="map-canvas__info-window">
          <v-theme-provider theme="light">
            <div class="map-canvas__info-card">
              <PlaceCard
                :place="showPoint"
                :show-add="showAdd"
                :index="showPointIndex"
                :context="showPointContext"
                compact
                @submit-add-history="emit('submit-add-history', { passPlace: showPoint })" />
            </div>
          </v-theme-provider>
        </div>
      </InfoWindow>
    </GoogleMap>

    <div class="map-legend" role="group" aria-label="Map layers">
      <button
        v-for="item in legend"
        :key="item.key"
        type="button"
        class="map-legend__item"
        :class="{ 'map-legend__item--off': !props.layers[item.key] }"
        :aria-pressed="props.layers[item.key]"
        :title="props.layers[item.key] ? `Hide ${item.label.toLowerCase()}` : `Show ${item.label.toLowerCase()}`"
        @click="emit('toggle-layer', item.key)">
        <span class="map-legend__swatch" :style="item.swatch" aria-hidden="true" />
        {{ item.label }}
      </button>
      <span v-if="options.length > 0 && props.layers.rec" class="map-legend__key">
        <span
          class="map-legend__swatch"
          :style="{ background: 'white', border: `2px solid ${palette.accent}` }"
          aria-hidden="true" />
        Other options for stop {{ (props.openStep ?? 0) + 1 }}
      </span>
    </div>
  </div>
</template>

<style scoped>
  .map-canvas__info-card {
    min-width: 220px;
    max-width: 320px;
  }

  /* Deep overrides for Google Maps InfoWindow */
  :deep(.gm-style-iw-c) {
    background-color: #ffffff !important;
    padding: 0 !important;
    border-radius: 8px !important;
    box-shadow: 0 6px 18px rgba(0, 0, 0, 0.4) !important;
  }

  :deep(.gm-style-iw-d) {
    overflow: hidden !important;
    max-height: none !important;
  }

  :deep(.gm-style-iw-tc::after) {
    background-color: #ffffff !important;
  }

  :deep(.gm-ui-hover-effect) {
    top: 4px !important;
    right: 4px !important;
    background: rgba(var(--v-theme-surface), 0.8) !important;
    border-radius: 50% !important;
  }

  .map-canvas {
    height: 100%;
    position: relative;
    width: 100%;
  }

  /* Bottom-left, clear of Google's logo; doubles as the layer switch. */
  .map-legend {
    align-items: center;
    background: rgb(var(--v-theme-surface));
    border: 1px solid rgba(var(--v-border-color), 0.22);
    border-radius: 8px;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.12);
    bottom: 32px;
    display: flex;
    flex-wrap: wrap;
    gap: 2px 4px;
    left: 12px;
    max-width: calc(100% - 24px);
    padding: 4px;
    position: absolute;
    z-index: 5;
  }

  .map-legend__item,
  .map-legend__key {
    align-items: center;
    border-radius: 6px;
    color: rgb(var(--v-theme-on-surface));
    display: inline-flex;
    font-size: 0.8rem;
    gap: 6px;
    padding: 4px 8px;
  }

  .map-legend__item {
    background: none;
    border: 0;
    cursor: pointer;
  }

  .map-legend__item:hover {
    background: rgba(var(--v-theme-on-surface), 0.06);
  }

  .map-legend__item:focus-visible {
    outline: 2px solid rgb(var(--v-theme-primary));
    outline-offset: -2px;
  }

  .map-legend__item--off {
    color: rgba(var(--v-theme-on-surface), 0.5);
    text-decoration: line-through;
  }

  .map-legend__item--off .map-legend__swatch {
    opacity: 0.35;
  }

  .map-legend__key {
    color: rgba(var(--v-theme-on-surface), 0.72);
  }

  .map-legend__swatch {
    border-radius: 50%;
    box-sizing: border-box;
    display: inline-block;
    height: 12px;
    width: 12px;
  }
</style>
