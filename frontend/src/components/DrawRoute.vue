<script lang="ts" setup>
  import { ref, watch, computed } from "vue"
  import type { GowallaPlace } from "@/types/place"
  import { decode } from "@googlemaps/polyline-codec"
  import { Polyline, InfoWindow } from "vue3-google-map"
  import { api } from "@/api"
  import { palette } from "@/styles/palette"

  interface PathInfo {
    path: { lat: number; lng: number }[]
    midPoint: { lat: number; lng: number } | null
    duration: string
    distance: number
    type: string
  }

  const props = defineProps<{
    points: GowallaPlace[]
    type: string
    color?: string
    innerColor?: string
    highlighted?: boolean
  }>()

  const showPath = ref<PathInfo | null>(null)
  const closeRoute = ref(false)
  const showInfo = ref(false)
  const infoPosition = ref<{ lat: number; lng: number } | null>(null)
  const isHovering = ref(false)
  const emphasized = computed(() => isHovering.value || Boolean(props.highlighted))

  // Without a road route (no routing key, or the routing service is down), the points are
  // joined by straight lines, drawn thinner; a duration of "0s" keeps the travel-time
  // popup closed for them.
  const straightPath = (points: GowallaPlace[]): PathInfo | null => {
    const path = points
      .filter((p) => p && p.latitude != null && p.longitude != null)
      .map((p) => ({ lat: p.latitude, lng: p.longitude }))
    if (path.length < 2) return null
    return { path, midPoint: null, duration: "0s", distance: 0, type: "STRAIGHT" }
  }

  const handleRouteClick = (event: any) => {
    if (event.latLng) {
      infoPosition.value = { lat: event.latLng.lat(), lng: event.latLng.lng() }
      showInfo.value = true
    }
  }

  const fetchRoutePath = async (points: GowallaPlace[], type: string): Promise<PathInfo | null> => {
    if (!points || points.length < 2 || !points[0] || !points[1]) {
      return null
    }

    try {
      const time = new Date().toISOString()
      const res = (await api.post("/route/", { points: points, time: time, type: type })).data
      const route = res["route"]
      if (!route) return null

      const encodedPolyline = route.polyline.encodedPolyline
      const decodedTuple = decode(encodedPolyline)
      const path = decodedTuple.map((point) => ({ lat: point[0], lng: point[1] }))

      if (path.length === 0) return null
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
    if (!props.points) return ""
    return props.points.map((p) => p?.raw_poi_id).join(",")
  })

  watch(
    () => propsPointStr.value,
    async () => {
      showPath.value =
        (await fetchRoutePath(
          props.points,
          // props.type === "hist" ? "WALK" : "TRANSIT"
          "DRIVE",
        )) ?? straightPath(props.points)
    },
    { immediate: true },
  )

  const formatTime = (time: string | null) => {
    if (!time) return ""
    const sec = Number(time.slice(0, time.length - 1))
    const min = Math.floor(sec / 60)
    const hour = Math.floor(min / 60)
    const day = Math.floor(hour / 24)
    if (day > 0) return day + " day"
    if (hour > 0) return hour + " hr " + (min % 60 === 0 ? "" : (min % 60) + " min")
    return (
      (min % 60 === 0 ? "" : (min % 60) + " min ") + (sec % 60 === 0 ? "" : (sec % 60) + " sec")
    )
  }
</script>

<template>
  <template v-if="showPath && showPath.path.length > 0">
    <!-- Base Line (Solid) -->
    <Polyline
      :options="{
        path: showPath.path,
        strokeColor: props.type === 'hist' ? palette.neutralStrong : palette.accentStrong,
        strokeOpacity: emphasized ? 0.8 : 1,
        strokeWeight: (emphasized ? 10 : 7) - (showPath.type === 'STRAIGHT' ? 3 : 0),
        zIndex: emphasized ? 3 : 1,
        cursor: 'pointer',
      }"
      @click="handleRouteClick"
      @mouseover="isHovering = true"
      @mouseout="isHovering = false" />
    <Polyline
      :options="{
        path: showPath.path,
        strokeColor: props.type === 'hist' ? palette.neutralSoft : palette.accent,
        strokeOpacity: 1,
        strokeWeight: (emphasized ? 7 : 5) - (showPath.type === 'STRAIGHT' ? 2 : 0),
        zIndex: emphasized ? 4 : 2,
        cursor: 'pointer',
      }"
      @click="handleRouteClick"
      @mouseover="isHovering = true"
      @mouseout="isHovering = false" />
    <InfoWindow
      v-if="infoPosition && showPath.duration !== '0s' && !closeRoute && showInfo"
      :options="{ position: infoPosition, headerDisabled: true }">
      <div class="route-info-window">
        <v-icon
          :icon="
            showPath.type === 'DRIVE'
              ? 'mdi-car'
              : showPath.type === 'WALK'
                ? 'mdi-walk'
                : 'mdi-bus-multiple'
          "
          size="25"
          color="#333333" />
        <div style="color: #333333 !important">
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
          class="mx-1 route-info-window__close"
          variant="text"
          @click="showInfo = false" />
      </div>
    </InfoWindow>
  </template>
</template>

<style scoped>
  .route-info-window {
    color: #333333;
    font-size: 0.75rem;
    font-weight: 500;
    display: flex;
    gap: 8px;
    align-items: center;
    padding: 4px 8px;
  }

  :deep(.gm-style-iw-c) {
    background-color: #ffffff !important;
    padding: 0 !important;
  }

  :deep(.gm-style-iw-d) {
    overflow: hidden !important;
  }

  :deep(.gm-style-iw-tc::after) {
    background-color: #ffffff !important;
  }

  .route-info-window__close {
    color: #666666 !important;
  }
</style>
