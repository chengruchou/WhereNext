<script lang="ts" setup>
  import { ref, onMounted, computed, watch } from "vue"
  import type { GowallaPlace } from "@/types/place"
  import { decode } from "@googlemaps/polyline-codec"
  import { Polyline } from "vue3-google-map"
  import axios from "axios"
  const api = axios.create({ baseURL: "http://127.0.0.1:5000/api" })
  const apiKey = import.meta.env.VITE_GOOGLE_API_KEY
  const props = defineProps<{
    userHist: GowallaPlace[]
  }>()
  const routePath = ref<{ lat: number; lng: number }[]>([])
  watch(
    () => props.userHist,
    async (newSeq, oldSeq) => {
      try {
        console.log("fetch route ", newSeq)
        const res = (await api.post("/route/", newSeq)).data
        console.log("route resp ", res)
        const decodedTuple = decode(res.polyline.encodedPolyline)
        routePath.value = decodedTuple.map((point) => ({ lat: point[0], lng: point[1] }))
        console.log("routePath ", routePath.value)
      } catch (error) {
        console.log(error)
      }
    },
    { deep: true },
  )
</script>

<template>
  <Polyline 
    v-if="routePath.length" 
    :options="{ 
      path: routePath,
      strokeColor: 'Black',
      strokeOpacity: 1,
      strokeWeight: 11,
      zIndex: 1
    }" 
  />

  <Polyline 
    v-if="routePath.length" 
    :options="{ 
      path: routePath,
      strokeColor: '#470DFA',
      strokeOpacity: 1,
      strokeWeight: 8,
      zIndex: 2
    }" 
  />
</template>
