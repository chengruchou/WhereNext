<script lang="ts" setup>
  import { ref, onMounted, computed, watch } from "vue"
  import axios from "axios"
  import UserLogin from "./components/UserLogin.vue"
  import HistoryList from "./components/HistoryList.vue"
  import MapCanvas from "./components/MapCanvas.vue"
  import SearchPanel from "./components/SearchPanel.vue"
  import PlaceCard from "./components/PlaceCard.vue"
  import type { PlaceInfo } from "./types/place"

  const apiKey = import.meta.env.VITE_GOOGLE_API_KEY
  const api = axios.create({ baseURL: "http://127.0.0.1:5000/api" })
  const userHistory = ref<PlaceInfo[]>()
  const userId = ref("")
  const showSearch = ref<PlaceInfo | null>(null)
  const showRecommend = ref<PlaceInfo[]>([])

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

  const addUserHistory = async (payload: { passPlace: PlaceInfo | null }) => {
    try {
      const place = payload.passPlace
      const msg = (await api.post(`/db/add/${userId.value}`, place)).data
      console.log("add db ", msg)
      fetchUserHistory({ passUserId: userId.value })
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

  const getNextPOI = async () => {
    try {
      const res = (await api.get(`/model/genpoi/${userId.value}`)).data
      console.log("got POI res", res)
      showRecommend.value = res as PlaceInfo[]
    } catch (error) {
      alert(error)
    }
  }
</script>

<template>
  <v-app>
    <v-navigation-drawer permanent width="600">
      <v-row>
        <v-col>
          <UserLogin @submit-user-id="fetchUserHistory" />
          <HistoryList :user-history="userHistory" />
          <SearchPanel @submit-search-place="searchPlaceId" />
          <PlaceCard :place="showSearch" :show-add="true" @submit-add-history="addUserHistory" />
        </v-col>
        <v-col class="d-flex flex-column align-center">
          <v-btn text="Get next POIs" @click="getNextPOI" class="my-4" color="primary" />
          <span v-for="e in showRecommend" :key="e.name">
            <PlaceCard :place="e" :show-add="false" />
          </span>
        </v-col>
      </v-row>
    </v-navigation-drawer>
    <v-main>
      <MapCanvas />
    </v-main>
  </v-app>
</template>
