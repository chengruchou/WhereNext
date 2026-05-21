<script lang="ts" setup>
  import { ref, reactive, watch, computed } from "vue"
  import type { GowallaPlace } from "@/types/place"
  import { GoogleMap, AdvancedMarker, InfoWindow } from "vue3-google-map"
  import DrawRoute from "./DrawRoute.vue"
  import PlaceCard from "./PlaceCard.vue"

  const apiKey = import.meta.env.VITE_GOOGLE_API_KEY
  const props = defineProps<{
    showSearch: GowallaPlace[]
    showRecommend: GowallaPlace[]
    userHist: GowallaPlace[]
    focusedPlace: GowallaPlace | null
  }>()
  const emit = defineEmits<{
    (e: "submit-add-history", payload: { passPlace: GowallaPlace | null }): void
  }>()

  const center = ref({ lat: 39.0528237667, lng: -94.59031105 })
  const mapRef = ref<any>(null)
  const layers = reactive({ hist: true, search: true, rec: true })
  const filters = [
    { key: "hist", label: "History", color: "cyan-darken-2" },
    { key: "search", label: "Search", color: "orange-darken-3" },
    { key: "rec", label: "Recommend", color: "yellow-darken-3" },
  ] as const

  const showPoint = ref<GowallaPlace | null>(null)
  const showAdd = ref(true)

  const addHistory = async (place: GowallaPlace) => {
    emit("submit-add-history", { passPlace: place })
  }

  const visiblePoints = computed(() => {
    const points: GowallaPlace[] = []
    if (layers.hist && props.userHist) points.push(...props.userHist)
    if (layers.search && props.showSearch) points.push(...props.showSearch)
    if (layers.rec && props.showRecommend) points.push(...props.showRecommend)

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
  <div style="position: relative; width: 100%; height: 100%">
    <div
      style="
        position: absolute;
        bottom: 24px;
        left: 50%;
        transform: translateX(-50%);
        z-index: 1000;
      "
      class="d-flex align-center bg-white rounded-pill elevation-3 px-2 py-1">
      <v-btn
        v-for="f in filters"
        :key="f.key"
        variant="tonal"
        rounded="pill"
        size="small"
        class="mx-1"
        :color="layers[f.key] ? f.color : 'grey'"
        @click="layers[f.key] = !layers[f.key]">
        {{ f.label }}
      </v-btn>
    </div>

    <GoogleMap
      ref="mapRef"
      :api-key="apiKey"
      map-id="CenterMap"
      style="width: 100%; height: 100%"
      :center="center"
      :zoom="15"
      @click="showPoint = null">
      <template v-if="layers.hist">
        <DrawRoute :points="props.userHist" :type="'hist'" />
        <AdvancedMarker
          v-for="(e, index) in props.userHist"
          :key="e.raw_poi_id"
          :options="{
            position: { lat: e.latitude, lng: e.longitude },
            title: `${index + 1}. ${e.raw_poi_id} ${e.category_name}`,
          }"
          :pinOptions="{ background: 'cyan', glyphText: String(index + 1), glyphColor: 'black' }"
          @click="((showPoint = e), (showAdd = false))" />
      </template>

      <template v-if="layers.search">
        <AdvancedMarker
          v-for="e in props.showSearch"
          :key="'search-' + e.raw_poi_id"
          :options="{
            position: { lat: e.latitude, lng: e.longitude },
            title: `${e.raw_poi_id} ${e.category_name}`,
          }"
          :pinOptions="{ background: 'orange' }"
          @click="((showPoint = e), (showAdd = true))" />
      </template>

      <template v-if="layers.rec">
        <DrawRoute
          v-if="props.userHist?.length && props.showRecommend?.length"
          :points="[props.userHist.at(-1)!, props.showRecommend[0]]"
          :type="'rec'" />
        <AdvancedMarker
          v-for="(e, index) in props.showRecommend"
          :key="'rec-' + e.raw_poi_id"
          :options="{
            position: { lat: e.latitude, lng: e.longitude },
            title: `${index + 1}. ${e.raw_poi_id} ${e.category_name}`,
          }"
          :pinOptions="{
            background: 'yellow',
            glyphText: String(index + 1),
            glyphColor: 'black',
          }"
          @click="((showPoint = e), (showAdd = true))" />
      </template>

      <InfoWindow
        v-if="showPoint"
        :options="{
          position: { lat: showPoint.latitude, lng: showPoint.longitude },
          headerDisabled: true,
        }">
        <div style="zoom: 0.8">
          <PlaceCard
            :place="showPoint"
            :show-add="showAdd"
            :index="0"
            @submit-add-history="addHistory(showPoint)" />
        </div>
      </InfoWindow>
    </GoogleMap>
  </div>
</template>
