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
  const allCat = ref<string[]>([])
  const activeEvidenceTab = ref<"history" | "search">("history")
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
        activeEvidenceTab.value = "history"
        console.log("search result ", userHistory.value)
      } else {
        userId.value = null
        userHistory.value = []
        userHistPlace.value = []
        showSearch.value = []
        noSearchRes.value = false
        focusedPlace.value = null
        activeEvidenceTab.value = "history"
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
        activeEvidenceTab.value = "search"
      } else {
        noSearchRes.value = true
        showSearch.value = []
        activeEvidenceTab.value = "search"
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
      if (Array.isArray(res) && res.length > 0) {
        noSearchRes.value = false
        showSearch.value = res
        activeEvidenceTab.value = "search"
      } else {
        noSearchRes.value = true
        showSearch.value = []
        activeEvidenceTab.value = "search"
      }
    } catch (error) {
      alert(error)
    }
  }

  const clearSearchResults = () => {
    showSearch.value = []
    noSearchRes.value = false
    activeEvidenceTab.value = "search"
  }

  const getNextPOI = async () => {
    isInferring.value = true
    try {
      for (let i = 0; i < 3; i++) {
        const res = (await api.post(`/model/genpoi/${userId.value}`, { append_back: topIds.value }))
          .data
        console.log("got POI res", res)
        showRecommend.value.push(res)
        nowRecRound.value = showRecommend.value.length - 1
      }
      isChatPanelOpen.value = true
      getExplanation()
    } catch (error) {
      alert(error)
    } finally {
      isInferring.value = false
    }
  }

  const handleFocusPlace = async (payload: { focusPlace: GowallaPlace | null }) => {
    focusedPlace.value = null
    await nextTick()
    focusedPlace.value = payload.focusPlace
  }

  const getExplanation = async () => {
    isExplaining.value = true
    try {
      const res = (
        await api.post("/chat/explain", { hists: userHistPlace.value, recs: showRecommend.value })
      ).data
      showStr.value = res
    } catch (error) {
      alert(error)
    } finally {
      isExplaining.value = false
    }
  }
</script>

<template>
  <v-app class="research-app">
    <v-app-bar class="research-app__bar" color="surface" density="compact" elevation="1">
      <template v-slot:prepend>
        <v-app-bar-nav-icon color="primary" @click="drawer = !drawer"></v-app-bar-nav-icon>
      </template>

      <v-app-bar-title class="research-app__title">
        Trajectory-aware POI Recommendation
      </v-app-bar-title>

      <v-spacer />

      <v-chip size="small" variant="tonal" color="primary" class="research-app__time">
        {{ currentTime }}
      </v-chip>
    </v-app-bar>

    <v-navigation-drawer v-model="drawer" permanent width="720" class="research-drawer">
      <div class="research-drawer__grid">
        <section class="research-drawer__column research-drawer__column--context">
          <div class="research-drawer__controls">
            <UserLogin @submit-user-id="fetchUserHistory" />

            <SearchPanel
              @submit-search-place-id="searchPlaceId"
              @submit-search-place-cat="searchPlaceCat"
              @clear-search-results="clearSearchResults"
              :no-search-res="noSearchRes"
              :all-cat="allCat" />
          </div>

          <section class="evidence-panel">
            <v-tabs
              v-model="activeEvidenceTab"
              color="primary"
              density="compact"
              grow
              class="evidence-panel__tabs">
              <v-tab value="history" class="evidence-panel__tab">
                History
                <v-chip size="x-small" variant="tonal" color="secondary" class="ml-2">
                  {{ userHistory.length }}
                </v-chip>
              </v-tab>
              <v-tab value="search" class="evidence-panel__tab">
                Search
                <v-chip size="x-small" variant="tonal" color="warning" class="ml-2">
                  {{ showSearch.length }}
                </v-chip>
              </v-tab>
            </v-tabs>

            <v-window v-model="activeEvidenceTab" class="evidence-panel__window">
              <v-window-item value="history" class="evidence-panel__item">
                <HistoryList
                  :user-history="userHistory"
                  @delete-all="delUserHistory"
                  @delete-one="delOneHistory"
                  @focus-place="handleFocusPlace" />
              </v-window-item>

              <v-window-item value="search" class="evidence-panel__item">
                <section class="search-results">
                  <div class="search-results__header">
                    <div>
                      <div class="text-overline text-warning font-weight-bold">Search Results</div>
                      <h2 class="search-results__title">Retrieved Candidates</h2>
                    </div>

                    <v-chip size="small" variant="tonal" color="warning" class="search-results__count">
                      {{ showSearch.length }} POIs
                    </v-chip>
                  </div>

                  <div class="search-results__body">
                    <div v-if="!showSearch || showSearch.length === 0" class="search-results__empty">
                      <v-icon icon="mdi-database-search-outline" size="30" color="warning" />
                      <div class="search-results__empty-title">No retrieved candidates</div>
                      <div class="search-results__empty-text">Search by POI ID or category.</div>
                    </div>

                    <div v-else class="d-flex flex-column">
                      <PlaceCard
                        v-for="e in showSearch"
                        :key="e.raw_poi_id"
                        :place="e"
                        :show-add="true"
                        :index="0"
                        context="search"
                        @submit-add-history="addUserHistory"
                        @focus-place="handleFocusPlace"
                        density="compact" />
                    </div>
                  </div>
                </section>
              </v-window-item>
            </v-window>
          </section>
        </section>

        <section class="research-drawer__column research-drawer__column--model">
          <RecommendPanel
            :recommendations="showRecommend"
            :is-inferring="isInferring"
            :hist="userHistPlace"
            @trigger-inference="getNextPOI"
            @update-currentRound="nowRecRound = $event"
            @focus-place="handleFocusPlace"
            @submit-add-history="addUserHistory" />
        </section>
      </div>
    </v-navigation-drawer>

    <v-main class="research-main">
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

<style scoped>
  .research-app {
    background: rgb(var(--v-theme-background));
  }

  .research-app__bar {
    border-bottom: 1px solid rgba(var(--v-border-color), 0.18);
  }

  .research-app__title {
    color: rgb(var(--v-theme-on-surface));
    font-size: 0.96rem;
    font-weight: 800;
    letter-spacing: 0;
  }

  .research-app__time {
    font-weight: 700;
    margin-right: 12px;
  }

  .research-drawer {
    border-right: 1px solid rgba(var(--v-border-color), 0.18);
  }

  .research-drawer__grid {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
    height: 100%;
    min-height: 0;
  }

  .research-drawer__column {
    min-height: 0;
    padding: 14px 14px 0;
  }

  .research-drawer__column--context {
    border-right: 1px solid rgba(var(--v-border-color), 0.18);
    display: flex;
    flex-direction: column;
    padding-bottom: 0;
  }

  .research-drawer__column--model {
    display: flex;
    flex-direction: column;
    padding-bottom: 14px;
  }

  .research-drawer__controls {
    flex-shrink: 0;
  }

  .evidence-panel {
    display: flex;
    flex: 1 1 auto;
    flex-direction: column;
    margin: 0 4px 14px;
    min-height: 0;
  }

  .evidence-panel__tabs {
    background: rgb(var(--v-theme-surface));
    border: 1px solid rgba(var(--v-border-color), 0.22);
    flex-shrink: 0;
  }

  .evidence-panel__tab {
    font-weight: 800;
    letter-spacing: 0;
    min-width: 0;
  }

  .evidence-panel__window {
    flex: 1 1 auto;
    min-height: 0;
    overflow-y: auto;
    padding-top: 12px;
    scrollbar-gutter: stable;
    scrollbar-width: thin;
  }

  .evidence-panel__window::-webkit-scrollbar {
    width: 6px;
  }

  .evidence-panel__window::-webkit-scrollbar-track {
    background: transparent;
  }

  .evidence-panel__window::-webkit-scrollbar-thumb {
    background: rgba(var(--v-theme-on-surface), 0.24);
    border-radius: 999px;
  }

  .evidence-panel__item {
    min-height: 100%;
  }

  .search-results {
    margin: 0;
  }

  .search-results__header {
    align-items: flex-start;
    border-bottom: 1px solid rgba(var(--v-border-color), 0.18);
    display: flex;
    gap: 12px;
    justify-content: space-between;
    padding: 2px 2px 10px;
  }

  .search-results__title {
    color: rgb(var(--v-theme-on-surface));
    font-size: 1.05rem;
    font-weight: 800;
    line-height: 1.25;
    margin: 0;
  }

  .search-results__count {
    flex-shrink: 0;
    font-weight: 700;
    margin-top: 4px;
  }

  .search-results__body {
    background: rgb(var(--v-theme-surface));
    border: 1px solid rgba(var(--v-border-color), 0.22);
    margin-top: 12px;
    min-height: 170px;
    overflow: visible;
    padding: 8px 4px;
  }

  .search-results__empty {
    align-items: center;
    display: flex;
    flex-direction: column;
    justify-content: center;
    min-height: 150px;
    padding: 20px 16px;
    text-align: center;
  }

  .search-results__empty-title {
    color: rgb(var(--v-theme-on-surface));
    font-size: 0.9rem;
    font-weight: 800;
    margin-top: 10px;
  }

  .search-results__empty-text {
    color: rgba(var(--v-theme-on-surface), 0.68);
    font-size: 0.76rem;
    line-height: 1.35;
    margin-top: 3px;
  }

  .research-main {
    min-height: 0;
  }

  @media (max-width: 1200px) {
    :deep(.research-drawer) {
      width: 660px !important;
    }

    .research-drawer__column {
      padding-left: 12px;
      padding-right: 12px;
    }
  }
</style>
