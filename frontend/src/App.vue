<script lang="ts" setup>
  import { ref, onMounted, nextTick } from "vue"
  import { api, errorMessage } from "./api"
  import TravelerPanel from "./components/TravelerPanel.vue"
  import MapCanvas from "./components/MapCanvas.vue"
  import SearchPanel from "./components/SearchPanel.vue"
  import RecommendPanel from "./components/RecommendPanel.vue"
  import IntentPanel from "./components/IntentPanel.vue"
  import type {
    GroundedResponse,
    RouteEvidence,
    RouteResponse,
    VerifiedExplanation,
  } from "./types/evidence"
  import type { Intent, IntentParseResponse, SteeringControls } from "./types/intent"
  import type { GowallaPlace, UserHistory } from "./types/place"

  const userHistory = ref<UserHistory[]>([])
  const userHistPlace = ref<GowallaPlace[]>([])
  const userId = ref<number | null>(null)
  const showSearch = ref<GowallaPlace[]>([])
  const showRecommend = ref<GowallaPlace[][]>([])
  // The stop whose details are open, and the one under the pointer; shared by panel and map.
  const openStep = ref<number | null>(null)
  const hoveredStep = ref<number | null>(null)
  const noSearchRes = ref(false)
  const isInferring = ref(false)
  const focusedPlace = ref<GowallaPlace | null>(null)
  const leftDrawer = ref(true)
  const isExplaining = ref(false)
  const explanation = ref<VerifiedExplanation | null>(null)
  const explainModel = ref("")
  const explainError = ref("")
  const allCat = ref<string[]>([])
  const intent = ref<Intent | null>(null)
  const intentControls = ref<SteeringControls | null>(null)
  const isParsingIntent = ref(false)
  const intentError = ref("")
  const routeEvidence = ref<RouteEvidence | null>(null)

  // Map layers, switched from the map's legend.
  const layers = ref({ hist: true, search: true, rec: true })

  // Failed calls are reported in one notice at the bottom of the screen.
  const notice = ref({ show: false, text: "" })
  const report = (action: string, error: unknown) => {
    console.error(error)
    notice.value = { show: true, text: errorMessage(action, error) }
  }

  onMounted(async () => {
    allCat.value = await fetchAllCat()
  })

  const fetchAllCat = async () => {
    try {
      return (await api.get("/poi/allcat")).data
    } catch (error) {
      report("Couldn't load place types", error)
      return []
    }
  }

  const fetchUserHistory = async (payload: { passUserId: number | null }) => {
    try {
      showRecommend.value = []
      openStep.value = null
      hoveredStep.value = null
      routeEvidence.value = null
      explanation.value = null
      explainError.value = ""
      if (payload.passUserId || payload.passUserId === 0) {
        console.log("search user ", payload.passUserId)
        userId.value = payload.passUserId
        const res = (await api.get(`/user/${userId.value}`)).data
        userHistory.value = res.userHist
        userHistPlace.value = res.userHistPlace
        console.log("search result ", userHistory.value)
      } else {
        userId.value = null
        userHistory.value = []
        userHistPlace.value = []
        showSearch.value = []
        noSearchRes.value = false
        focusedPlace.value = null
      }
    } catch (error) {
      report("Couldn't load this traveler's visits", error)
    }
  }

  const delUserHistory = async () => {
    try {
      const res = (await api.delete(`/user/${userId.value}`)).data
      console.log(res)
      fetchUserHistory({ passUserId: userId.value })
    } catch (error) {
      report("Couldn't delete the visits", error)
    }
  }

  const delOneHistory = async (payload: { delId: number }) => {
    try {
      const res = (await api.delete(`/user/delone/${payload.delId}`)).data
      console.log(res)
      fetchUserHistory({ passUserId: userId.value })
    } catch (error) {
      report("Couldn't delete the visit", error)
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
      report("Couldn't add the visit", error)
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
        showSearch.value = []
      }
    } catch (error) {
      report("Couldn't search by place ID", error)
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
      } else {
        noSearchRes.value = true
        showSearch.value = []
      }
    } catch (error) {
      report("Couldn't search by place type", error)
    }
  }

  const clearSearchResults = () => {
    showSearch.value = []
    noSearchRes.value = false
  }

  const canPlan = () => userId.value != null && userHistPlace.value.length > 0

  // Reading a request also plans the route, when there is a user to plan from.
  const parseIntent = async (payload: { query: string }) => {
    isParsingIntent.value = true
    intentError.value = ""
    try {
      const res = (await api.post<IntentParseResponse>("/intent/parse", { query: payload.query }))
        .data
      intent.value = res.intent
      intentControls.value = res.controls
    } catch (error) {
      console.error(error)
      intentError.value = "Could not read the request. Try shorter wording."
      return
    } finally {
      isParsingIntent.value = false
    }
    if (canPlan()) getNextPOI()
  }

  const clearIntent = () => {
    intent.value = null
    intentControls.value = null
    intentError.value = ""
  }

  const editIntent = (payload: { intent: Intent }) => {
    intent.value = payload.intent
    if (canPlan() && showRecommend.value.length > 0) getNextPOI()
  }

  // One call plans every stop; rounds[i][0] is the stop chosen at step i.
  const getNextPOI = async () => {
    isInferring.value = true
    try {
      const res = (
        await api.post<RouteResponse>(`/model/route/${userId.value}`, {
          intent: intent.value ?? undefined,
        })
      ).data
      console.log("got route", res)
      openStep.value = null
      hoveredStep.value = null
      showRecommend.value = res.rounds
      routeEvidence.value = res.evidence
      intentControls.value = res.evidence.intent ? res.evidence.controls : intentControls.value
      getExplanation()
    } catch (error) {
      report("Couldn't plan the route", error)
    } finally {
      isInferring.value = false
    }
  }

  const handleFocusPlace = async (payload: { focusPlace: GowallaPlace | null }) => {
    focusedPlace.value = null
    await nextTick()
    focusedPlace.value = payload.focusPlace
  }

  // The explanation is written from the route evidence and checked sentence by sentence;
  // the route panel shows the checked sentences under each stop.
  const getExplanation = async () => {
    const evidence = routeEvidence.value
    if (!evidence) return
    isExplaining.value = true
    explanation.value = null
    explainError.value = ""
    try {
      const res = (await api.post<GroundedResponse | string>("/chat/grounded", { evidence })).data
      if (routeEvidence.value !== evidence) return // a newer route is being explained
      if (typeof res === "string") {
        explainError.value = res
      } else {
        explanation.value = res.explanation
        explainModel.value = res.model
      }
    } catch (error) {
      if (routeEvidence.value !== evidence) return
      // Shown in the route panel's footer rather than as a notice: the route itself is fine.
      explainError.value = errorMessage("Couldn't write the explanation", error)
    } finally {
      if (routeEvidence.value === evidence) isExplaining.value = false
    }
  }
</script>

<template>
  <v-app class="research-app">
    <v-app-bar class="research-app__bar" color="surface" density="compact" elevation="1">
      <template v-slot:prepend>
        <v-app-bar-nav-icon
          :aria-label="leftDrawer ? 'Hide planning panel' : 'Show planning panel'"
          @click="leftDrawer = !leftDrawer"></v-app-bar-nav-icon>
      </template>

      <v-app-bar-title class="research-app__title">
        <span class="text-primary">where</span><span class="text-on-surface">next</span>
      </v-app-bar-title>

    </v-app-bar>

    <v-snackbar v-model="notice.show" location="bottom" :timeout="8000" color="error" multi-line>
      {{ notice.text }}
      <template #actions>
        <v-btn variant="text" @click="notice.show = false">Close</v-btn>
      </template>
    </v-snackbar>

    <!-- One planning panel, top to bottom: traveler, request, route. -->
    <v-navigation-drawer v-model="leftDrawer" permanent width="400" class="research-drawer">
      <div class="research-drawer__content">
        <TravelerPanel
          :user-id="userId"
          :user-history="userHistory"
          @submit-user-id="fetchUserHistory"
          @delete-all="delUserHistory"
          @delete-one="delOneHistory"
          @focus-place="handleFocusPlace" />

        <IntentPanel
          :intent="intent"
          :controls="intentControls"
          :is-parsing="isParsingIntent"
          :parse-error="intentError"
          @submit-request="parseIntent"
          @clear-request="clearIntent"
          @edit-intent="editIntent" />

        <RecommendPanel
          :recommendations="showRecommend"
          :is-inferring="isInferring"
          :hist="userHistPlace"
          :evidence="routeEvidence"
          :explanation="explanation"
          :explain-model="explainModel"
          :explain-error="explainError"
          :is-explaining="isExplaining"
          v-model:open-step="openStep"
          :hovered-step="hoveredStep"
          @hover-step="hoveredStep = $event"
          @trigger-inference="getNextPOI"
          @focus-place="handleFocusPlace"
          @submit-add-history="addUserHistory" />
      </div>
    </v-navigation-drawer>

    <v-main class="research-main">
      <div class="research-main__stage">
        <MapCanvas
          :show-recommend="showRecommend"
          :show-search="showSearch"
          :user-hist="userHistPlace"
          :focused-place="focusedPlace"
          :layers="layers"
          :open-step="openStep"
          :hovered-step="hoveredStep"
          :travel-mode="routeEvidence?.intent?.travel_mode ?? 'drive'"
          @toggle-layer="layers[$event] = !layers[$event]"
          @select-step="openStep = $event"
          @submit-add-history="addUserHistory" />

        <SearchPanel
          class="research-main__search"
          :no-search-res="noSearchRes"
          :all-cat="allCat"
          :results="showSearch"
          :can-add="userId != null"
          @submit-search-place-id="searchPlaceId"
          @submit-search-place-cat="searchPlaceCat"
          @clear-search-results="clearSearchResults"
          @focus-place="handleFocusPlace"
          @submit-add-history="addUserHistory" />
      </div>
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
    font-size: 1.25rem;
    font-weight: 700;
    letter-spacing: -0.03em;
    text-transform: lowercase;
  }

  .research-drawer {
    background: rgb(var(--v-theme-surface));
    border-right: 1px solid rgba(var(--v-border-color), 0.18);
  }

  /* The whole panel scrolls as one column: traveler, request, then the route. */
  .research-drawer__content {
    padding: 16px;
  }

  .research-main {
    min-height: 0;
  }

  /* v-main spans the window under the panel and bar; the stage is just the map's area. */
  .research-main__stage {
    height: 100%;
    position: relative;
  }

  .research-main__search {
    left: 12px;
    position: absolute;
    top: 12px;
    width: min(380px, calc(100% - 24px));
    z-index: 5;
  }
</style>
