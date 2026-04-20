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
  const userHistPlace = ref<GowallaPlace[]>([])
  const userId = ref<number | null>(null)
  const showSearch = ref<GowallaPlace[]>([])
  const showRecommend = ref<GowallaPlace[]>([])
  const noSearchRes = ref(false)
  const isInferring = ref(false)
  const currentTime = ref(new Date().toLocaleString("zh-TW", { hour12: false }))
  const focusedPlace = ref<GowallaPlace | null>(null)

  const allCat = ref([])

  onMounted(async () => {
    const timer = setInterval(() => {
      currentTime.value = new Date().toLocaleString("zh-TW", { hour12: false })
    }, 1000)
    allCat.value = await fetchAllCat()
    onUnmounted(() => clearInterval(timer))
  })

  const fetchAllCat = async () => {
    try {
      console.log("Fetching All Cat")
      return (await api.get("/poi/allcat")).data
    } catch (error) {
      alert(error)
      return []
    }
  }

  const fetchUserHistory = async (payload: { passUserId: number | null }) => {
    try {
      if (payload.passUserId || payload.passUserId === 0) {
        console.log("search user ", payload.passUserId)
        userId.value = payload.passUserId
        const res = (await api.get(`/user/${userId.value}`)).data
        userHistory.value = res.userHist
        userHistPlace.value = res.userHistPlace
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

  const delOneHistory = async (payload: { delId: number }) => {
    try {
      const res = (await api.delete(`/user/delone/${payload.delId}`)).data
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

  const searchPlaceId = async (payload: { passPlaceId: number | null }) => {
    try {
      console.log("Search place Id ", payload.passPlaceId)
      const res = (await api.post("/poi/id", { id: payload.passPlaceId })).data
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

  const searchPlaceCat = async (payload: { passPlaceCat: string | null }) => {
    try {
      console.log("Search place Category ", payload.passPlaceCat)
      const res = (await api.post("/poi/cat", { cat: payload.passPlaceCat })).data
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
      isInferring.value = true
      const res = (await api.get(`/model/genpoi/${userId.value}`)).data
      isInferring.value = false
      console.log("got POI res", res)
      showRecommend.value = res
    } catch (error) {
      alert(error)
    }
  }

  const handleFocusPlace = (payload: { focusPlace: GowallaPlace | null }) => {
    focusedPlace.value = payload.focusPlace
  }
</script>

<template>
  <v-app>
    <v-app-bar title="POI" color="secondary" density="compact">
      {{ currentTime }}<v-spacer> </v-spacer>
    </v-app-bar>

    <v-navigation-drawer permanent width="600">
      <v-row class="fill-height ma-0">
        
        <v-col cols="6" class="d-flex flex-column h-100 border-e pa-3 pb-0">
          
        <div class="flex-shrink-0 d-flex flex-column">
            <UserLogin @submit-user-id="fetchUserHistory" />
            
            <HistoryList
              :user-history="userHistory"
              @delete-all="delUserHistory"
              @delete-one="delOneHistory"
              @focus-place="handleFocusPlace"
            />
            
            <SearchPanel
              @submit-search-place-id="searchPlaceId"
              @submit-search-place-cat="searchPlaceCat"
              :no-search-res="noSearchRes"
              :all-cat="allCat" 
            />
          </div>

          <div class="text-warning text-overline mt-2 mb-0 px-4">
              Search Results
            </div>

            <div class="flex-grow-1 overflow-y-auto px-4 pb-4">
              
              <div v-if="!showSearch || showSearch.length === 0" class="text-grey text-center mt-4">
                Awaiting search...
              </div>

              <div v-else class="d-flex flex-column">
                <PlaceCard
                  v-for="e in showSearch"
                  :place="e"
                  :show-add="true"
                  :index="0"
                  @submit-add-history="addUserHistory"
                  @focus-place="handleFocusPlace"
                  density="compact"
                />
              </div>

            </div>
        </v-col>

        <v-col cols="6" class="d-flex flex-column h-100 pa-3">
          
          <v-btn
            text="Get next POIs"
            @click="getNextPOI"
            class="mb-4 flex-shrink-0"
            color="primary"
            :loading="isInferring" 
          />
          
          <div class="flex-grow-1 overflow-y-auto pr-1">
            <div class="d-flex flex-column">
              <PlaceCard 
                v-for="(e, idx) in showRecommend" 
                :key="e.raw_poi_id || idx" 
                :place="e" 
                :show-add="false" 
                :index="idx" 
                @focus-place="handleFocusPlace"
              />
            </div>
          </div>
        </v-col>

      </v-row>
    </v-navigation-drawer>

    <v-main>
      <MapCanvas :show-recommend="showRecommend" :show-search="showSearch" :user-hist="userHistPlace" :focused-place="focusedPlace" />
    </v-main>
  </v-app>
</template>
