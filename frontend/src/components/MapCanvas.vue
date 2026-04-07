<script lang="ts" setup>
  import { ref, onMounted, computed, watch } from "vue"
  import { GoogleMap, AdvancedMarker } from "vue3-google-map"
  const apiKey = import.meta.env.VITE_GOOGLE_API_KEY
  const center = { lat: 23.001121896510238, lng: 120.22314068661719 }
</script>

<template>
  <GoogleMap
    :api-key="apiKey"
    map-id="CenterMap"
    style="width: 100%; height: 100%"
    :center="center"
    :zoom="15">
    <AdvancedMarker :options="{ position: center, title: '敬業一舍' }" />
  </GoogleMap>
</template>
