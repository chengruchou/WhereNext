<script lang="ts" setup>
  import { ref, onMounted, computed, watch } from "vue"
  import type { GowallaPlace } from "@/types/place"
  import { GoogleMap, AdvancedMarker } from "vue3-google-map"
  import DrawRoute from "./DrawRoute.vue"
  const apiKey = import.meta.env.VITE_GOOGLE_API_KEY
  const props = defineProps<{
    showSearch: GowallaPlace[]
    showRecommend: GowallaPlace[]
    userHist: GowallaPlace[]
    focusedPlace: GowallaPlace | null
  }>()
  const center = ref({ lat: 39.0528237667, lng: -94.59031105 })

  const updateCenter = (newList: GowallaPlace[]) => {
    if (newList && newList.length > 0) {
      center.value = {
        lat: newList[0].latitude,
        lng: newList[0].longitude,
      }
    }
  }

  watch(
    () => props.showSearch,
    (newVal) => updateCenter(newVal),
    { deep: true },
  )
  watch(
    () => props.showRecommend,
    (newVal) => updateCenter(newVal),
    { deep: true },
  )
  watch(
    () => props.userHist,
    (newVal) => updateCenter(newVal),
    { deep: true },
  )
  watch(
    () => props.focusedPlace,
    (newVal) => {
      if (newVal) {
        center.value = {
          lat: newVal.latitude,
          lng: newVal.longitude,
        }
      }
    },
    { deep: true },
  )
</script>

<template>
  <GoogleMap
    :api-key="apiKey"
    map-id="CenterMap"
    style="width: 100%; height: 100%"
    :center="center"
    :zoom="15">
    <DrawRoute :user-hist="props.userHist" />
    <span v-for="e in props.userHist">
      <AdvancedMarker
        :options="{
          position: { lat: e.latitude, lng: e.longitude },
          title: String(e.raw_poi_id + ' ' + e.category_name),
        }"
        :pinOptions="{ background: 'cyan' }">
      </AdvancedMarker>
    </span>
    <span v-for="e in props.showSearch">
      <AdvancedMarker
        :options="{
          position: { lat: e.latitude, lng: e.longitude },
          title: String(e.raw_poi_id + ' ' + e.category_name),
        }"
        :pinOptions="{ background: 'orange' }">
      </AdvancedMarker>
    </span>
    <span v-for="e in props.showRecommend">
      <AdvancedMarker
        :options="{
          position: { lat: e.latitude, lng: e.longitude },
          title: String(e.raw_poi_id + ' ' + e.category_name),
        }"
        :pinOptions="{ background: 'blue' }">
      </AdvancedMarker>
    </span>
  </GoogleMap>
</template>
