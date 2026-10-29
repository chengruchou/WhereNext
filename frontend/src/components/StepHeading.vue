<script lang="ts" setup>
  // The numbered heading of a step in the planning panel; a label when it names a field.
  defineProps<{
    step: number
    title: string
    labelFor?: string
  }>()
</script>

<template>
  <component :is="labelFor ? 'label' : 'h2'" :for="labelFor" class="step-heading">
    <span class="step-heading__number" aria-hidden="true">{{ step }}</span>
    <span>{{ title }}</span>
  </component>
</template>

<style scoped>
  .step-heading {
    align-items: center;
    color: rgb(var(--v-theme-on-surface));
    display: flex;
    font-size: 0.95rem;
    font-weight: 700;
    gap: 8px;
    line-height: 1.3;
    margin: 0 0 8px;
  }

  .step-heading__number {
    align-items: center;
    background: rgba(var(--v-theme-primary), 0.14);
    border-radius: 50%;
    color: rgb(var(--v-theme-primary));
    display: inline-flex;
    flex-shrink: 0;
    font-size: 0.75rem;
    font-weight: 700;
    height: 20px;
    justify-content: center;
    width: 20px;
  }
</style>
