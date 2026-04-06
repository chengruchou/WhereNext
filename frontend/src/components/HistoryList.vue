<script lang="ts" setup>
import { ref, onMounted, computed, watch } from "vue";
import axios from "axios";
const userId = ref("");
const props = defineProps<{ userHistory: number[] | undefined }>();
</script>

<template>
  <v-card title="User History">
    <v-item>
      
      <v-list>
        <v-list-item v-for="(e, index) in props.userHistory" :key="index">
          <v-list-item-title>
            History # {{ index + 1 }}
          </v-list-item-title>
          <v-list-item-subtitle>
            Site ID : {{ e }}
          </v-list-item-subtitle>
        </v-list-item>
      </v-list>
    </v-item>
  </v-card>
</template>
