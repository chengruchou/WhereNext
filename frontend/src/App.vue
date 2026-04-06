<script lang="ts" setup>
import { ref, onMounted, computed, watch } from "vue";
import axios from "axios";
const apiKey = import.meta.env.VITE_GOOGLE_API_KEY;
import UserLogin from "./components/UserLogin.vue";
import HistoryList from "./components/HistoryList.vue";
const api = axios.create({ baseURL: "http://127.0.0.1:5000/api" });
const userHistory = ref<number[]>()
const userId = ref('')

const fetchUserHistory = async (payload: {passId: string}) => {
  try{
    userId.value = payload.passId
    userHistory.value = (await api.get(`/db/fetch/${userId.value}`)).data
  }
  catch(error){
    alert(error)
  }
}
</script>

<template>
  <v-app>
    <v-main>
      <v-navigation-drawer>
        <UserLogin @submit-user-id="fetchUserHistory"/>
        <history-list :user-history="userHistory"/>
      </v-navigation-drawer>
    </v-main>
  </v-app>
</template>
