<script lang="ts" setup>
  import { ref, watch, computed } from "vue"
  import type { GowallaPlace } from "@/types/place"
  import { decode } from "@googlemaps/polyline-codec"
  import { Polyline, InfoWindow } from "vue3-google-map"
  import axios from "axios"

  interface PathInfo {
    path: { lat: number; lng: number }[]
    midPoint: { lat: number; lng: number } | null
    duration: string
    distance: number
    type: string
  }

  const api = axios.create({ baseURL: "http://127.0.0.1:5000/api" })
  const props = defineProps<{
    points: GowallaPlace[]
    type: string
  }>()

  const showPath = ref<PathInfo | null>(null)
  const closeRoute = ref(false)

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
        } else {
          type = "WALK"
        }
      }
      const encodedPolyline = route.polyline.encodedPolyline
      const decodedTuple = decode(encodedPolyline)
      const path = decodedTuple.map((point) => ({ lat: point[0], lng: point[1] }))

      if (path.length === 0) {
        return null
      }

      const midPoint = path[Math.floor(path.length / 2)]

      return {
        path,
        midPoint,
        duration: route.duration,
        distance: route.distanceMeters,
        type: type,
      }
    } catch (error) {
      console.error(error)
      return null
    }
  }

  const propsPointStr = computed(() => {
    if (!props.points) {
      return []
    }
    return props.points.map((p) => p?.raw_poi_id).join(",")
  })

  watch(
    () => propsPointStr,
    async (newSeq) => {
      showPath.value = await fetchRoutePath(
        props.points,
        // props.type === "hist" ? "WALK" : "TRANSIT",
        "WALK"
      )
    },
    { deep: true, immediate: true },
  )

  const formatTime = (time: string | null) => {
    if (!time) {
      return ""
    }
    const sec = Number(time.slice(0, time.length - 1))
    const min = Math.floor(sec / 60)
    const hour = Math.floor(min / 60)
    const day = Math.floor(hour / 24)
    if (day > 0) {
      return day + " day"
    }
    if (hour > 0) {
      return hour + " hr " + (min % 60 === 0 ? "" : (min % 60) + " min")
    }
    return (
      (min % 60 === 0 ? "" : (min % 60) + " min ") + (sec % 60 === 0 ? "" : (sec % 60) + " sec")
    )
  }
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
      v-if="showPath.midPoint && showPath.duration !== '0s' && !closeRoute"
      :options="{ position: showPath.midPoint, headerDisabled: true }">
      <div
        style="
          color: black;
          font-size: 12px;
          font-weight: 500;
          display: flex;
          gap: 5px;
          align-items: center;
        ">
        <v-icon :icon="showPath.type == 'WALK' ? 'mdi-walk' : 'mdi-bus-multiple'" size="25" />
        <div>
          {{ formatTime(showPath.duration) }}<br />
          {{
            showPath.distance > 1000
              ? (showPath.distance / 1000).toFixed(2) + " km "
              : showPath.distance + " m "
          }}
        </div>
        <v-btn
          icon="mdi-close-box"
          size="10"
          class="mx-1"
          variant="text"
          @click="closeRoute = true" />
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
