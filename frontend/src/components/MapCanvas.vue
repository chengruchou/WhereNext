<script lang="ts" setup>
  import { ref, onMounted, computed, watch } from "vue"
  import type { GowallaPlace } from "@/types/place"
  import { GoogleMap, AdvancedMarker } from "vue3-google-map"
  const apiKey = import.meta.env.VITE_GOOGLE_API_KEY
  const props = defineProps<{ showSearch: GowallaPlace | null; showRecommend: GowallaPlace[] }>()
  const center = computed(() => {
    if (props.showSearch == null) return { lat: 39.0528237667, lng: -94.59031105 }
    else return { lat: props.showSearch.latitude, lng: props.showSearch.longitude }
  })
</script>

<template>
  <GoogleMap
    :api-key="apiKey"
    map-id="CenterMap"
    style="width: 100%; height: 100%"
    :center="center"
    :zoom="15">
    <AdvancedMarker
      v-if="props.showSearch"
      :options="{
        position: center,
        title: String(props.showSearch.raw_poi_id + ' ' + props.showSearch.category_name),
      }">
    </AdvancedMarker>
    <span v-for="e in props.showRecommend">
      <AdvancedMarker
        :options="{ position: { lat: e.latitude, lng: e.longitude }, title: String(e.raw_poi_id + ' ' + e.category_name) }"
        :pinOptions="{ background: 'yellow' }">
      </AdvancedMarker>
    </span>
  </GoogleMap>
</template>
