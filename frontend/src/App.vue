<script lang="ts" setup>
  import { ref, onMounted, computed, watch } from "vue"
  import { GoogleMap, AdvancedMarker } from "vue3-google-map"
  import axios from "axios"
  import UserLogin from "./components/UserLogin.vue"
  import HistoryList from "./components/HistoryList.vue"

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

  const searchPlace = async () => {
    const requestBody = {
      textQuery: "小東公園",
      languageCode: "zh-TW",
      // locationRestriction: {
      //   rectangle: {
      //     low: {
      //       latitude: 40.477398,
      //       longitude: -74.259087,
      //     },
      //     high: {
      //       latitude: 40.91618,
      //       longitude: -73.70018,
      //     },
      //   },
      // },
    }

    const requestConfig = {
      headers: {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": apiKey,
        "X-Goog-FieldMask":
          "places.attributions, places.id, places.name, nextPageToken, places.movedPlace, places.movedPlaceId",
      },
    }
    try {
      let res = (
        await axios.post(
          "https://places.googleapis.com/v1/places:searchText",
          requestBody,
          requestConfig,
        )
      ).data
      console.log("search place res : " + res)
    } catch (error) {
      console.log(error)
    }
  }
</script>

<template>
  <v-app>
    <v-navigation-drawer permanent width="300">
      <UserLogin @submit-user-id="fetchUserHistory" />
      <history-list :user-history="userHistory" />
    </v-navigation-drawer>
    <v-main>
      <GoogleMap
        :api-key="apiKey"
        map-id="CenterMap"
        style="width: 100%; height: 100%"
        :center="center"
        :zoom="15">
        <AdvancedMarker :options="{ position: center, title: '敬業一舍' }" />
      </GoogleMap>
    </v-main>
  </v-app>
</template>
