<script lang="ts" setup>
  import { ref, reactive, watch, computed } from "vue"
  import type { GowallaPlace } from "@/types/place"
  import { GoogleMap, AdvancedMarker, InfoWindow } from "vue3-google-map"
  import DrawRoute from "./DrawRoute.vue"
  import PlaceCard from "./PlaceCard.vue"

  const apiKey = import.meta.env.VITE_GOOGLE_API_KEY
  const props = defineProps<{
    showSearch: GowallaPlace[]
    showRecommend: GowallaPlace[][]
    nowRecRound: number
    userHist: GowallaPlace[]
    focusedPlace: GowallaPlace | null
    layers: { hist: boolean; search: boolean; rec: boolean }
  }>()
  const emit = defineEmits<{
    (e: "submit-add-history", payload: { passPlace: GowallaPlace | null }): void
  }>()

  const center = ref({ lat: 39.0528237667, lng: -94.59031105 })
  const mapRef = ref<any>(null)

  const showPoint = ref<GowallaPlace | null>(null)
  const showPointIndex = ref(0)
  const showPointContext = ref<"search" | "recommendation" | "history">("search")
  const showAdd = ref(true)

  const addHistory = async (place: GowallaPlace) => {
    emit("submit-add-history", { passPlace: place })
  }
  const topPlaces = computed(() => {
    return props.showRecommend
      .map((round) => {
        if (round && round.length > 0) {
          return round[0]
        }
        return null
      })
      .filter((p): p is GowallaPlace => p !== null)
  })
  const recRoutes = computed(() => {
    const routes: GowallaPlace[][] = []
    if (
      props.userHist &&
      props.userHist.length > 0 &&
      props.showRecommend &&
      props.nowRecRound >= 0
    ) {
      let lastPlace = props.userHist[props.userHist.length - 1]
      for (let i: number = 0; i <= props.nowRecRound; i++) {
        if (!props.showRecommend[i] || !props.showRecommend[i][0]) continue
        routes.push([lastPlace, props.showRecommend[i][0]])
        lastPlace = props.showRecommend[i][0]
      }
    }
    return routes
  })

  const visiblePoints = computed(() => {
    const points: GowallaPlace[] = []
    if (props.layers.hist && props.userHist) points.push(...props.userHist)
    if (props.layers.search && props.showSearch) points.push(...props.showSearch)
    if (props.layers.rec && props.showRecommend && props.showRecommend[props.nowRecRound]) {
      points.push(...props.showRecommend[props.nowRecRound])
    }
    if (props.layers.rec && topPlaces) points.push(...topPlaces.value)

    return points.filter((p) => p && p.latitude != null && p.longitude != null)
  })

  const fitMapToVisiblePoints = (places: GowallaPlace[]) => {
    if (!places.length || !mapRef.value?.map) return

    if (places.length === 1) {
      center.value = { lat: places[0].latitude, lng: places[0].longitude }
      mapRef.value.map.panTo(center.value)
      mapRef.value.map.setZoom(15)
      return
    }
    let minLat = 90
    let maxLat = -90
    let minLng = 180
    let maxLng = -180
    places.forEach((p) => {
      if (p.latitude < minLat) minLat = p.latitude
      if (p.latitude > maxLat) maxLat = p.latitude
      if (p.longitude < minLng) minLng = p.longitude
      if (p.longitude > maxLng) maxLng = p.longitude
    })
    mapRef.value.map.fitBounds({
      south: minLat,
      north: maxLat,
      west: minLng,
      east: maxLng,
    })
  }

  watch(
    visiblePoints,
    (newPoints) => {
      setTimeout(() => fitMapToVisiblePoints(newPoints), 100)
    },
    { deep: true, immediate: true },
  )

  watch(
    () => props.focusedPlace,
    (newVal) => {
      if (newVal && mapRef.value?.map) {
        center.value = { lat: newVal.latitude, lng: newVal.longitude }
        mapRef.value.map.panTo(center.value)
        mapRef.value.map.setZoom(15)
      }
    },
    { deep: true },
  )
</script>

<template>
  <div class="map-canvas">
    <GoogleMap
      ref="mapRef"
      :api-key="apiKey"
      map-id="506622965fe133bac9a880a1"
      style="width: 100%; height: 100%"
      :center="center"
      :zoom="15"
      :disable-default-ui="true"
      @click="showPoint = null">
      <template v-if="props.layers.hist">
        <DrawRoute :points="props.userHist" :type="'hist'" />
        <AdvancedMarker
          v-for="(e, index) in props.userHist"
          :key="e.raw_poi_id"
          :options="{
            position: { lat: e.latitude, lng: e.longitude },
            title: `History ${index + 1}: ${e.category_name}`,
          }"
          :pinOptions="{
            background: '#470DFA',
            glyphText: String(index + 1),
            glyphColor: 'white',
            borderColor: '#000000',
            scale: 0.8,
          }"
          @click="
            ((showPoint = e),
            (showAdd = false),
            (showPointIndex = index),
            (showPointContext = 'history'))
          " />
      </template>

      <template v-if="props.layers.search">
        <AdvancedMarker
          v-for="(e, index) in props.showSearch"
          :key="'search-' + e.raw_poi_id"
          :options="{
            position: { lat: e.latitude, lng: e.longitude },
            title: `Search: ${e.category_name}`,
          }"
          :pinOptions="{
            background: '#FF6D00',
            borderColor: '#E65100',
            scale: 0.7,
          }"
          @click="
            ((showPoint = e),
            (showAdd = true),
            (showPointIndex = index),
            (showPointContext = 'search'))
          " />
      </template>

      <template v-if="props.layers.rec">
        <DrawRoute
          v-for="(e, idx) in recRoutes"
          :key="idx"
          v-if="topPlaces.length > 0"
          :points="e"
          :type="'rec'" />

        <template v-for="(es, roundId) in props.showRecommend">
          <template v-if="roundId == nowRecRound">
            <template v-for="(e, index) in es" :key="'rec-' + roundId + '-' + e.raw_poi_id">
              <AdvancedMarker
                v-if="index === 0 || (props.focusedPlace && props.focusedPlace.raw_poi_id === e.raw_poi_id)"
                :options="{
                  position: { lat: e.latitude, lng: e.longitude },
                  title: `Round ${roundId + 1} Rec ${index + 1}: ${e.category_name}`,
                }"
                :pinOptions="{
                  background: '#2962FF',
                  glyphText: index === 0 ? String(roundId + 1) : String(index + 1),
                  glyphColor: 'white',
                  borderColor: '#1A237E',
                  scale: index === 0 ? 1.0 : 0.7,
                }"
                @click="
                  ((showPoint = e),
                  (showAdd = true),
                  (showPointIndex = index),
                  (showPointContext = 'recommendation'))
                " />
            </template>
          </template>
          <template v-else-if="roundId < nowRecRound">
            <AdvancedMarker
              :options="{
                position: { lat: es[0].latitude, lng: es[0].longitude },
                title: `Round ${roundId + 1}: ${es[0].category_name}`,
              }"
              :pinOptions="{
                background: roundId === 0 ? '#9FA8DA' : '#7986CB',
                glyphText: String(roundId + 1),
                glyphColor: 'white',
                borderColor: '#3F51B5',
                scale: 0.9,
              }"
              @click="
                ((showPoint = es[0]),
                (showAdd = true),
                (showPointIndex = 0),
                (showPointContext = 'recommendation'))
              " />
          </template>
        </template>
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
                @submit-add-history="addHistory(showPoint)" />
            </div>
          </v-theme-provider>
        </div>
      </InfoWindow>
    </GoogleMap>
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

  .map-layer-filter {
    align-items: center;
    background: rgba(var(--v-theme-surface), 0.9);
    backdrop-filter: blur(10px);
    border: 1px solid rgba(var(--v-border-color), 0.22);
    border-radius: 12px;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.25);
    display: flex;
    flex-direction: column;
    gap: 8px;
    padding: 12px 8px;
    position: absolute;
    right: 24px;
    /* Position above the ChatPanel (which starts at bottom: 24px and has a header) */
    bottom: 104px;
    width: auto;
    z-index: 1000;
  }

  .map-layer-filter__title {
    color: rgb(var(--v-theme-primary));
    font-size: 0.6rem;
    font-weight: 900;
    letter-spacing: 0.5px;
    margin-bottom: 4px;
    text-transform: uppercase;
    writing-mode: vertical-rl;
    transform: rotate(180deg);
  }

  .map-layer-filter__controls {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .map-layer-filter__button {
    border-radius: 8px !important;
  }

  @media (max-width: 700px) {
    .map-layer-filter {
      bottom: 74px;
      left: 12px;
      max-width: calc(100% - 24px);
      transform: none;
      width: auto;
    }

    .map-layer-filter__controls {
      grid-template-columns: 1fr;
    }
  }
</style>
