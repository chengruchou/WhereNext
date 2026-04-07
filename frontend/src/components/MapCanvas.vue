<script lang="ts" setup>
  import { ref, onMounted, computed, watch } from "vue"
  import type { PlaceInfo } from "@/types/place"
  import { GoogleMap, AdvancedMarker } from "vue3-google-map"
  const apiKey = import.meta.env.VITE_GOOGLE_API_KEY
  const props = defineProps<{ showSearch: PlaceInfo | null; showRecommend: PlaceInfo[]}>()
  const center = computed(() => {
    if(props.showSearch == null)
      return { lat: 23.001121896510238, lng: 120.22314068661719 }
    else
      return { lat: props.showSearch.lat, lng: props.showSearch.lng }
  })
</script>

<template>
  <GoogleMap
    :api-key="apiKey"
    map-id="CenterMap"
    style="width: 100%; height: 100%"
    :center=center
    :zoom="15">
    <AdvancedMarker v-if="props.showSearch" :options="{ position: center, title: props.showSearch?.name }" />
    <span v-for="e in props.showRecommend">
    <AdvancedMarker :options="{ position: { lat: e.lat, lng:e.lng }, title: e.name }" :pinOptions="{ background:'yellow'}" />
    </span>
  </GoogleMap>
</template>
