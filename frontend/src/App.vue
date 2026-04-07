<script lang="ts" setup>
  import { ref, onMounted, computed, watch } from "vue"
  import axios from "axios"
  import UserLogin from "./components/UserLogin.vue"
  import HistoryList from "./components/HistoryList.vue"
  import MapCanvas from "./components/MapCanvas.vue"
  import SearchPanel from "./components/SearchPanel.vue"
  import PlaceCard from "./components/PlaceCard.vue"
  interface PlaceInfo {
    name: string
    lat: number
    lng: number
    types: string[]
    photoUrl: string | null
  }

  const apiKey = import.meta.env.VITE_GOOGLE_API_KEY
  const api = axios.create({ baseURL: "http://127.0.0.1:5000/api" })
  const userHistory = ref<number[]>()
  const userId = ref("")
  const center = { lat: 23.001121896510238, lng: 120.22314068661719 }
  const showSearch = ref<PlaceInfo | null>(null)
  const showRecommend = ref<PlaceInfo[]>()

  const fetchUserHistory = async (payload: { passUserId: string }) => {
    try {
      userId.value = payload.passUserId
      if (userId.value) {
        userHistory.value = (await api.get(`/db/fetch/${userId.value}`)).data
      }
    } catch (error) {
      alert(error)
    }
  }

  const searchPlaceId = async (payload: { passPlaceName: string }) => {
    const requestBody = {
      textQuery: payload.passPlaceName,
      languageCode: "zh-TW",
      locationRestriction: {
        rectangle: {
          low: {
            latitude: 22,
            longitude: 120,
          },
          high: {
            latitude: 25,
            longitude: 122,
          },
        },
      },
    }
    const requestConfig = {
      headers: {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": apiKey,
        "X-Goog-FieldMask": "places.id",
      },
    }
    try {
      const res = (
        await axios.post(
          "https://places.googleapis.com/v1/places:searchText",
          requestBody,
          requestConfig,
        )
      ).data
      console.log("search place res : ", res)
      showSearch.value = await searchPlaceDetail(res.places[0].id)
    } catch (error) {
      console.log(error)
    }
  }

  const searchPlaceDetail = async (passId: string): Promise<PlaceInfo | null> => {
    const requestConfig = {
      headers: {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": apiKey,
        "X-Goog-FieldMask": "photos,location,types,displayName",
      },
    }
    try {
      const res = (
        await axios.get(
          `https://places.googleapis.com/v1/places/${passId}?languageCode=zh-TW`,
          requestConfig,
        )
      ).data
      console.log("search id res : ", res)
      return {
        name: res.displayName.text,
        lat: res.location.latitude,
        lng: res.location.longitude,
        types: res.types,
        photoUrl: `https://places.googleapis.com/v1/${res.photos[0].name}/media?key=${apiKey}&maxHeightPx=400&maxWidthPx=400`,
      }
    } catch (error) {
      console.log(error)
      return null
    }
  }
</script>

<template>
  <v-app>
    <v-navigation-drawer permanent width="300">
      <UserLogin @submit-user-id="fetchUserHistory" />
      <HistoryList :user-history="userHistory" />
      <SearchPanel @submit-search-place="searchPlaceId" />
      <PlaceCard :place="showSearch" />
    </v-navigation-drawer>
    <v-main>
      <MapCanvas />
    </v-main>
  </v-app>
</template>
