<script lang="ts" setup>
  import { ref, watch } from "vue"
  import type { GowallaPlace } from "@/types/place"
  import { decode } from "@googlemaps/polyline-codec"
  import { Polyline, InfoWindow } from "vue3-google-map"
  import axios from "axios"

  interface PathInfo {
    path: { lat: number; lng: number }[]
    midPoint: { lat: number; lng: number } | null
    duration: string | null
    distance: string | null
  }

  const api = axios.create({ baseURL: "http://127.0.0.1:5000/api" })
  const apiKey = import.meta.env.VITE_GOOGLE_API_KEY
  const props = defineProps<{
    userHist: GowallaPlace[]
    showRecommend: GowallaPlace[]
  }>()
  const histPath = ref<PathInfo | null>(null)
  const recPath = ref<PathInfo | null>(null)

  const fetchRoutePath = async (points: GowallaPlace[], type: string): Promise<PathInfo | null> => {
    if (!points || points.length < 2) return null

    try {
      console.log("fetch route ", points)
      const time = new Date().toISOString()
      const res = (await api.post("/route/", { points: points, time: time, type: type })).data
      const route = res["route"]
      const message = res["message"]
      if (message !== "success") {
        alert(message)
        if (!route) {
          return null
        }
      }
      const encodedPolyline = route.polyline.encodedPolyline
      const decodedTuple = decode(encodedPolyline)
      const path = decodedTuple.map((point) => ({ lat: point[0], lng: point[1] }))

      if (path.length === 0) return null

      const midPoint = path[Math.floor(path.length / 2)]

      return { path, midPoint, duration: route.duration, distance: route.distanceMeters }
    } catch (error) {
      console.error(error)
      return null
    }
  }

  watch(
    () => props.userHist,
    async (newSeq) => {
      histPath.value = await fetchRoutePath(newSeq, "WALK")
    },
    { deep: true },
  )

  watch(
    () => props.showRecommend,
    async (newSeq) => {
      const lastVisit = props.userHist[props.userHist.length - 1]
      recPath.value = await fetchRoutePath([lastVisit, newSeq[0]], "TRANSIT")
    },
    { deep: true },
  )
</script>

<template>
  <template v-if="histPath && histPath.path.length > 0">
    <Polyline
      :options="{
        path: histPath.path,
        strokeColor: 'Black',
        strokeOpacity: 1,
        strokeWeight: 11,
        zIndex: 1,
      }" />
    <Polyline
      :options="{
        path: histPath.path,
        strokeColor: '#470DFA',
        strokeOpacity: 1,
        strokeWeight: 8,
        zIndex: 2,
      }" />
    <InfoWindow
      v-if="histPath.midPoint"
      :options="{ position: histPath.midPoint, headerDisabled: true }">
      <div style="color: #202124; font-size: 12px; font-weight: 500">
        Duration: {{ histPath.duration }}<br />
        Distance: {{ histPath.distance }}m
      </div>
    </InfoWindow>
  </template>

  <template v-if="recPath && recPath.path.length > 0">
    <Polyline
      :options="{
        path: recPath.path,
        strokeColor: '#470DFA',
        strokeOpacity: 1,
        strokeWeight: 11,
        zIndex: 1,
      }" />
    <Polyline
      :options="{
        path: recPath.path,
        strokeColor: '#B6C8FF',
        strokeOpacity: 1,
        strokeWeight: 8,
        zIndex: 2,
      }" />
    <InfoWindow
      v-if="recPath.midPoint"
      :options="{ position: recPath.midPoint, headerDisabled: true }">
      <div style="color: #202124; font-size: 12px; font-weight: 500">
        Duration: {{ recPath.duration }}<br />
        Distance: {{ recPath.distance }}m
      </div>
    </InfoWindow>
  </template>
</template>

<style>
  /* 隱藏 InfoWindow 的關閉 (X) 按鈕 */
  .gm-ui-hover-effect {
    display: none !important;
  }

  /* 覆寫 InfoWindow 主容器的預設 padding，縮小整體框框 */
  .gm-style-iw-c {
    padding: 4px 8px !important;
    border-radius: 8px !important;
  }

  /* 取消 InfoWindow 內容區塊的額外留白與預設出現的滾動條 */
  .gm-style-iw-d {
    overflow: hidden !important;
    padding: 0 !important;
    margin: 0 !important;
  }

  .gm-style-iw-ch {
    display: none !important;
  }
</style>
