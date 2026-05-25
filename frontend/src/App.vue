<script lang="ts" setup>
  import { ref, onMounted, computed, watch, onUnmounted, nextTick } from "vue"
  import axios from "axios"
  import UserLogin from "./components/UserLogin.vue"
  import HistoryList from "./components/HistoryList.vue"
  import MapCanvas from "./components/MapCanvas.vue"
  import SearchPanel from "./components/SearchPanel.vue"
  import PlaceCard from "./components/PlaceCard.vue"
  import ChatPanel from "./components/ChatPanel.vue"
  import RecommendPanel from "./components/RecommendPanel.vue"
  import type { GowallaPlace, UserHistory } from "./types/place"

  const api = axios.create({ baseURL: "http://127.0.0.1:5000/api" })
  const userHistory = ref<UserHistory[]>([])
  const userHistPlace = ref<GowallaPlace[]>([])
  const userId = ref<number | null>(null)
  const showSearch = ref<GowallaPlace[]>([])
  const showRecommend = ref<GowallaPlace[][]>([])
  const nowRecRound = ref(0)
  const noSearchRes = ref(false)
  const isInferring = ref(false)
  const currentTime = ref(new Date().toLocaleString("zh-TW", { hour12: false }))
  const focusedPlace = ref<GowallaPlace | null>(null)
  const drawer = ref(true)
  const showStr = ref("")
  const isExplaining = ref(false)
  const isChatPanelOpen = ref(false)
  const allCat = ref([])
  const topIds = computed(() => {
    return showRecommend.value.map((round) => {
      if (round && round.length > 0) {
        return round[0].raw_poi_id
      }
      return null
    })
  })

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
      showRecommend.value = []
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
      console.log("add place ", payload.passPlace)
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
      const res = (await api.post("/poi/id", { id: payload.passPlaceId })).data[0]
      console.log("search place res : ", res)
      if (res && res.category_name) {
        noSearchRes.value = false
        showSearch.value = [res]
      } else {
        noSearchRes.value = true
      }
    } catch (error) {
      alert(error)
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
      alert(error)
    }
  }

  const getNextPOI = async () => {
    try {
      isInferring.value = true
      for (let i = 0; i < 3; i++) {
        const res = (await api.post(`/model/genpoi/${userId.value}`, { append_back: topIds.value }))
          .data
        console.log("got POI res", res)
        showRecommend.value.push(res)
        nowRecRound.value = showRecommend.value.length - 1
      }
      isInferring.value = false
      isChatPanelOpen.value = true
      getExplanation()
    } catch (error) {
      alert(error)
    }
  }

  const handleFocusPlace = async (payload: { focusPlace: GowallaPlace | null }) => {
    focusedPlace.value = null
    await nextTick()
    focusedPlace.value = payload.focusPlace
  }

  const getExplanation = async () => {
    try {
      isExplaining.value = true
      const res = (
        await api.post("/chat/explain", { hists: userHistPlace.value, recs: showRecommend.value })
      ).data
      showStr.value = res
      isExplaining.value = false
    } catch (error) {
      alert(error)
    }
  }
</script>

<template>
  <v-app>
    <v-app-bar title="POI" color="secondary" density="compact">
      <template v-slot:prepend>
        <v-app-bar-nav-icon @click="drawer = !drawer"></v-app-bar-nav-icon>
      </template>
      {{ currentTime }}<v-spacer> </v-spacer>
    </v-app-bar>

    <v-navigation-drawer v-model="drawer" permanent width="600">
      <v-row class="fill-height ma-0">
        <v-col cols="6" class="d-flex flex-column h-100 border-e pa-3 pb-0">
          <div class="flex-shrink-0 d-flex flex-column">
            <UserLogin @submit-user-id="fetchUserHistory" />

            <HistoryList
              :user-history="userHistory"
              @delete-all="delUserHistory"
              @delete-one="delOneHistory"
              @focus-place="handleFocusPlace" />

            <SearchPanel
              @submit-search-place-id="searchPlaceId"
              @submit-search-place-cat="searchPlaceCat"
              :no-search-res="noSearchRes"
              :all-cat="allCat" />
          </div>

          <div class="text-warning text-overline mt-2 mb-0 px-4">Search Results</div>

          <div class="flex-grow-1 overflow-y-auto px-4 pb-4" style="min-height: 400px">
            <div v-if="!showSearch || showSearch.length === 0" class="text-grey text-center mt-4">
              Awaiting search...
            </div>

            <div v-else class="d-flex flex-column">
              <PlaceCard
                v-for="e in showSearch"
                :place="e"
                :show-add="true"
                :index="0"
                context="search"
                @submit-add-history="addUserHistory"
                @focus-place="handleFocusPlace"
                density="compact" />
            </div>
          </div>
        </v-col>

        <v-col cols="6" class="d-flex flex-column h-100 pa-3">
          <RecommendPanel
            :recommendations="showRecommend"
            :is-inferring="isInferring"
            :hist="userHistPlace"
            @trigger-inference="getNextPOI"
            @update-currentRound="nowRecRound = $event"
            @focus-place="handleFocusPlace"
            @submit-add-history="addUserHistory" />
        </v-col>
      </v-row>
    </v-navigation-drawer>

    <v-main>
      <MapCanvas
        :show-recommend="showRecommend"
        :now-rec-round="nowRecRound"
        :show-search="showSearch"
        :user-hist="userHistPlace"
        :focused-place="focusedPlace"
        @submit-add-history="addUserHistory" />
      <ChatPanel v-model="isChatPanelOpen" :show-str="showStr" :is-explaining="isExplaining" />
    </v-main>
  </v-app>
</template>
