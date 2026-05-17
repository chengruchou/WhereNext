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
  const props = defineProps<{
    points: GowallaPlace[]
    type: string
  }>()

  const emit = defineEmits<{
    (e: "submit-view-port", paylaod: { passViewPort: any }): void
  }>()

  const showPath = ref<PathInfo | null>(null)

  const fetchRoutePath = async (points: GowallaPlace[], type: string): Promise<PathInfo | null> => {
    console.log("points : ", points)
    if (!points || points.length < 2 || !points[0] || !points[1]) {
      return null
    }

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

      if (path.length === 0) {
        return null
      }

      const midPoint = path[Math.floor(path.length / 2)]

      emit("submit-view-port", { passViewPort: route.viewport })

      return { path, midPoint, duration: route.duration, distance: route.distanceMeters }
    } catch (error) {
      console.error(error)
      return null
    }
  }

  watch(
    () => props.points,
    async (newSeq) => {
      showPath.value = await fetchRoutePath(newSeq, props.type === "hist" ? "WALK" : "TRANSIT")
    },
    { deep: true, immediate: true },
  )
</script>

<template>
  <template v-if="showPath && showPath.path.length > 0">
    <Polyline
      :options="{
        path: showPath.path,
        strokeColor: props.type === 'hist' ? 'black' : '#470DFA',
        strokeOpacity: 1,
        strokeWeight: 11,
        zIndex: 1,
      }" />
    <Polyline
      :options="{
        path: showPath.path,
        strokeColor: props.type === 'hist' ? '#470DFA' : '#B6C8FF',
        strokeOpacity: 1,
        strokeWeight: 8,
        zIndex: 2,
      }" />
    <InfoWindow
      v-if="showPath.midPoint"
      :options="{ position: showPath.midPoint, headerDisabled: true }">
      <div style="color: #202124; font-size: 12px; font-weight: 500">
        Duration: {{ showPath.duration }}<br />
        Distance: {{ showPath.distance }}m
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
