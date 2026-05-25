<script lang="ts" setup>
  import { marked } from "marked"
  import { computed, ref, watch } from "vue"

  const props = defineProps<{
    showStr: string
    isExplaining: boolean
    modelValue: boolean
  }>()

  const emit = defineEmits<{
    (e: "update:modelValue", value: boolean): void
  }>()

  const isOpen = ref(props.modelValue)

  watch(
    () => props.modelValue,
    (newVal) => {
      isOpen.value = newVal
    },
  )

  const togglePanel = () => {
    isOpen.value = !isOpen.value
    emit("update:modelValue", isOpen.value)
  }

  const allowedTags = new Set([
    "ARTICLE",
    "B",
    "BLOCKQUOTE",
    "BR",
    "CODE",
    "DIV",
    "EM",
    "H3",
    "H4",
    "HR",
    "I",
    "LI",
    "OL",
    "P",
    "PRE",
    "SECTION",
    "SPAN",
    "STRONG",
    "U",
    "UL",
  ])

  const sanitizeNode = (node: Node) => {
    const children = Array.from(node.childNodes)

    children.forEach((child) => {
      if (child.nodeType === Node.ELEMENT_NODE) {
        const element = child as HTMLElement

        if (!allowedTags.has(element.tagName)) {
          element.replaceWith(...Array.from(element.childNodes))
          return
        }

        Array.from(element.attributes).forEach((attribute) => {
          const name = attribute.name.toLowerCase()
          if (name.startsWith("on") || name === "style") {
            element.removeAttribute(attribute.name)
          }
        })

        sanitizeNode(element)
      } else if (child.nodeType !== Node.TEXT_NODE) {
        child.remove()
      }
    })
  }

  const structuredHtml = computed(() => {
    if (!props.showStr) return ""

    const renderedHtml = marked.parse(props.showStr, { async: false })
    const parser = new DOMParser()
    const document = parser.parseFromString(renderedHtml, "text/html")
    sanitizeNode(document.body)
    return document.body.innerHTML
  })
</script>

<template>
  <aside class="xai-panel">
    <v-card class="xai-panel__card" elevation="6" variant="outlined">
      <v-card-title
        class="xai-panel__header d-flex justify-space-between align-center cursor-pointer"
        @click="togglePanel">
        <div class="d-flex align-center min-w-0">
          <v-icon icon="mdi-text-box-search-outline" class="mr-2" size="20" />
          <div class="min-w-0">
            <div class="xai-panel__eyebrow">Interpretability</div>
            <div class="xai-panel__title">Recommendation Rationale</div>
          </div>
        </div>
        <v-btn
          :icon="isOpen ? 'mdi-chevron-down' : 'mdi-chevron-up'"
          size="small"
          variant="text"
          color="primary"
          @click.stop="togglePanel" />
      </v-card-title>

      <v-expand-transition>
        <div v-show="isOpen">
          <v-divider />
          <v-card-text class="xai-panel__body">
            <div v-if="isExplaining" class="xai-panel__state">
              <v-progress-circular indeterminate color="primary" size="30" />
              <span class="mt-3 text-caption text-medium-emphasis">Generating rationale</span>
            </div>

            <div v-else-if="showStr" class="xai-panel__content" v-html="structuredHtml"></div>

            <div v-else class="xai-panel__state">
              <v-icon icon="mdi-lightbulb-on-outline" size="28" color="primary" />
              <span class="mt-3 text-caption text-medium-emphasis">
                Waiting for recommendation output.
              </span>
            </div>
          </v-card-text>
        </div>
      </v-expand-transition>
    </v-card>
  </aside>
</template>

<style scoped>
  .xai-panel {
    bottom: 17px;
    position: absolute;
    right: 10px;
    width: 360px;
    z-index: 2000;
  }

  .xai-panel__card {
    background: rgb(var(--v-theme-surface));
    border-color: rgba(var(--v-border-color), 0.22);
  }

  .xai-panel__header {
    padding: 10px 14px;
  }

  .xai-panel__eyebrow {
    color: rgb(var(--v-theme-primary));
    font-size: 0.67rem;
    font-weight: 800;
    letter-spacing: 0;
    line-height: 1.1;
    text-transform: uppercase;
  }

  .xai-panel__title {
    color: rgb(var(--v-theme-on-surface));
    font-size: 0.95rem;
    font-weight: 800;
    line-height: 1.2;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .xai-panel__body {
    height: 300px;
    overflow-y: auto;
    padding: 14px;
  }

  .xai-panel__content {
    color: rgba(var(--v-theme-on-surface), 0.88);
    font-size: 0.86rem;
    line-height: 1.55;
  }

  .xai-panel__content :deep(h3),
  .xai-panel__content :deep(h4) {
    color: rgb(var(--v-theme-on-surface));
    font-size: 0.95rem;
    font-weight: 800;
    line-height: 1.25;
    margin: 0 0 8px;
  }

  .xai-panel__content :deep(p) {
    margin: 0 0 10px;
  }

  .xai-panel__content :deep(ul),
  .xai-panel__content :deep(ol) {
    margin: 0 0 10px;
    padding-left: 18px;
  }

  .xai-panel__content :deep(li) {
    margin: 4px 0;
  }

  .xai-panel__content :deep(strong),
  .xai-panel__content :deep(b) {
    color: rgb(var(--v-theme-on-surface));
    font-weight: 800;
  }

  .xai-panel__content :deep(code) {
    background: rgba(var(--v-theme-surface-variant), 0.42);
    border: 1px solid rgba(var(--v-border-color), 0.18);
    border-radius: 4px;
    font-size: 0.78rem;
    padding: 1px 4px;
  }

  .xai-panel__content :deep(blockquote) {
    border-left: 3px solid rgb(var(--v-theme-primary));
    color: rgba(var(--v-theme-on-surface), 0.78);
    margin: 0 0 10px;
    padding: 4px 0 4px 10px;
  }

  .xai-panel__state {
    align-items: center;
    display: flex;
    flex-direction: column;
    height: 100%;
    justify-content: center;
    text-align: center;
  }

  @media (max-width: 700px) {
    .xai-panel {
      bottom: 74px;
      left: 12px;
      right: 12px;
      width: auto;
    }
  }
</style>
