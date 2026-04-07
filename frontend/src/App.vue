<script lang="ts" setup>
  import { ref, onMounted, computed, watch } from "vue"
  import axios from "axios"
  import UserLogin from "./components/UserLogin.vue"
  import HistoryList from "./components/HistoryList.vue"
  import MapCanvas from "./components/MapCanvas.vue"
  import searchPanel from "./components/searchPanel.vue"

  const apiKey = import.meta.env.VITE_GOOGLE_API_KEY
  const api = axios.create({ baseURL: "http://127.0.0.1:5000/api" })
  const userHistory = ref<number[]>()
  const userId = ref("")
  const center = { lat: 23.001121896510238, lng: 120.22314068661719 }

  const fetchUserHistory = async (payload: { passId: string }) => {
    try {
      userId.value = payload.passId
      userHistory.value = (await api.get(`/db/fetch/${userId.value}`)).data
    } catch (error) {
      alert(error)
    }
  }

  const searchPlace = async (payload: { placeName: string }) => {
    const requestBody = {
      textQuery: payload.placeName,
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
      return res.places
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
      <history-list :user-history="userHistory" />
      <searchPanel @submit-search-place="searchPlace" />
    </v-navigation-drawer>
    <v-main>
      <MapCanvas />
    </v-main>
  </v-app>
</template>
