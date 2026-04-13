<script lang="ts" setup>
  import { ref, onMounted, computed, watch, onUnmounted } from "vue"
  import axios from "axios"
  import UserLogin from "./components/UserLogin.vue"
  import HistoryList from "./components/HistoryList.vue"
  import MapCanvas from "./components/MapCanvas.vue"
  import SearchPanel from "./components/SearchPanel.vue"
  import PlaceCard from "./components/PlaceCard.vue"
  import type { GowallaPlace, UserHistory } from "./types/place"

  const api = axios.create({ baseURL: "http://127.0.0.1:5000/api" })
  const userHistory = ref<UserHistory[]>([])
  const userId = ref<number | null>(null)
  const showSearch = ref<GowallaPlace | null>(null)
  const showRecommend = ref<GowallaPlace[]>([])
  const noSearchRes = ref(false)

  const currentTime = ref(new Date().toLocaleString("zh-TW", { hour12: false }))

  onMounted(() => {
    const timer = setInterval(() => {
      currentTime.value = new Date().toLocaleString("zh-TW", { hour12: false })
    }, 1000)

    onUnmounted(() => clearInterval(timer))
  })

  const fetchUserHistory = async (payload: { passUserId: number | null }) => {
    try {
      if (payload.passUserId || payload.passUserId === 0) {
        console.log("search user ", payload.passUserId)
        userId.value = payload.passUserId
        userHistory.value = (await api.get(`/user/${userId.value}`)).data
        console.log("search result ", userHistory.value)
      }
    } catch (error) {
      alert(error)
    }
  }

  const delUserHistory = async () => {
    try {
      const res = (await api.delete(`/user/${userId.value}`)).data
      console.log(res)
      fetchUserHistory({ passUserId: userId.value })
    } catch (error) {
      alert(error)
    }
  }

  const addUserHistory = async (payload: { passPlace: GowallaPlace | null }) => {
    try {
      const place = payload.passPlace
      const visitTimeISO = new Date().toISOString()
      const msg = (
        await api.post(`/user/${userId.value}`, {
          poi_id: place?.raw_poi_id,
          visit_time: visitTimeISO,
        })
      ).data
      console.log("add db ", msg)
      fetchUserHistory({ passUserId: userId.value })
    } catch (error) {
      alert(error)
    }
  }

  const searchPlace = async (payload: { passPlaceId: number | null }) => {
    try {
      console.log("Search place Id ", payload.passPlaceId)
      const res = (await api.post("/poi/", { id: payload.passPlaceId })).data
      console.log("search place res : ", res)
      if (res) {
        noSearchRes.value = false
        showSearch.value = res
      } else {
        noSearchRes.value = true
      }
    } catch (error) {
      console.log(error)
    }
  }

  const getNextPOI = async () => {
    try {
      const res = (await api.get(`/model/genpoi/${userId.value}`)).data
      console.log("got POI res", res)
      showRecommend.value = res
    } catch (error) {
      alert(error)
    }
  }
</script>

<template>
  <v-app>
    <v-app-bar title="POI">
      {{ currentTime }}
    </v-app-bar>
    <v-navigation-drawer permanent width="600">
      <v-row>
        <v-col>
          <UserLogin @submit-user-id="fetchUserHistory" />
          <HistoryList :user-history="userHistory" @handle-delete="delUserHistory" />
          <SearchPanel @submit-search-place="searchPlace" :no-search-res="noSearchRes" />
          <PlaceCard
            :place="showSearch"
            :show-add="true"
            :index="0"
            @submit-add-history="addUserHistory" />
        </v-col>
        <v-col class="d-flex flex-column">
          <v-btn text="Get next POIs" @click="getNextPOI" class="my-4 ma-3" color="primary" />
          <PlaceCard v-for="(e, idx) in showRecommend" :place="e" :show-add="false" :index="idx" />
        </v-col>
      </v-row>
    </v-navigation-drawer>
    <v-main>
      <MapCanvas :show-recommend="showRecommend" :show-search="showSearch" />
    </v-main>
  </v-app>
</template>
