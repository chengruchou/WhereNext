<script lang="ts" setup>
  import { computed, ref } from "vue"
  
  const userId = ref<number | null>(null)
  const isLoggedIn = ref(false)
  const formRef = ref<any>(null)

  const emit = defineEmits<{
    (e: "submit-user-id", payload: { passUserId: number | null }): void
  }>()

  const idRules = [
    (value: number | string | null) =>
      (value !== null && value !== "") || "User ID is required.",
    (value: number | string | null) =>
      Number.isInteger(Number(value)) || "User ID must be an integer.",
  ]

  const stateLabel = computed(() => isLoggedIn.value ? "Context loaded" : "Awaiting user")
  const stateColor = computed(() => isLoggedIn.value ? "success" : "primary")
  const actionLabel = computed(() => isLoggedIn.value ? "Logout" : "Login")

  const toggleLogin = async () => {
    if (isLoggedIn.value) {
      isLoggedIn.value = false
      userId.value = null
      emit("submit-user-id", { passUserId: null })
      
      if (formRef.value) formRef.value.resetValidation() 
    } else {
      const { valid } = await formRef.value.validate()
      
      if (!valid) return
      
      isLoggedIn.value = true
      emit("submit-user-id", { passUserId: userId.value })
    }
  }
</script>

<template>
  <section class="user-login">
    <div class="user-login__header">
      <div class="user-login__heading">
        <div class="text-overline text-primary font-weight-bold">User Context</div>
        <h2 class="user-login__title">User Trajectory</h2>
      </div>

      <v-chip
        size="small"
        variant="tonal"
        :color="stateColor"
        class="user-login__state">
        {{ stateLabel }}
      </v-chip>
    </div>

    <v-card class="user-login__card" elevation="0" variant="outlined">
      <v-card-text class="pa-3">
        <v-form ref="formRef" @submit.prevent="toggleLogin">
          <div class="user-login__form">
            <v-text-field 
              density="compact"  
              label="User ID"
              v-model.number="userId" 
              :readonly="isLoggedIn"
              :disabled="isLoggedIn"
              :rules="idRules"
              validate-on="submit"
              hide-details="auto"
              prepend-inner-icon="mdi-account-search-outline"
              variant="outlined"
            ></v-text-field>
          
            <v-btn 
              type="submit"
              :text="actionLabel"
              :color="isLoggedIn ? 'error' : 'primary'" 
              :prepend-icon="isLoggedIn ? 'mdi-close-circle-outline' : 'mdi-database-search-outline'"
              class="user-login__action"
            />
          </div>
        </v-form>
      </v-card-text>
    </v-card>

  </section>
</template>

<style scoped>
  .user-login {
    margin: 6px 4px 14px;
  }

  .user-login__header {
    align-items: flex-start;
    border-bottom: 1px solid rgba(var(--v-border-color), 0.18);
    display: flex;
    gap: 12px;
    justify-content: space-between;
    padding: 2px 2px 10px;
  }

  .user-login__heading {
    min-width: 0;
  }

  .user-login__title {
    color: rgb(var(--v-theme-on-surface));
    font-size: 1.05rem;
    font-weight: 800;
    line-height: 1.25;
    margin: 0;
  }

  .user-login__state {
    flex-shrink: 0;
    font-weight: 700;
    margin-top: 4px;
  }

  .user-login__card {
    background: rgb(var(--v-theme-surface));
    border-color: rgba(var(--v-border-color), 0.22);
    margin-top: 12px;
  }

  .user-login__form {
    align-items: flex-start;
    display: grid;
    gap: 10px;
    grid-template-columns: minmax(0, 1fr) 92px;
  }

  .user-login__action {
    font-weight: 800;
    height: 40px;
    letter-spacing: 0;
    min-width: 0;
  }

  @media (max-width: 720px) {
    .user-login__form {
      grid-template-columns: 1fr;
    }

    .user-login__action {
      width: 100%;
    }
  }
</style>
