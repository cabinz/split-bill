<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, useId } from 'vue'

export interface ColumnSelectOption {
  value: string
  label: string
}

const props = defineProps<{
  modelValue: string
  options: ColumnSelectOption[]
  detectedValue: string | null
  detectedLabel: string
  label: string
  placeholder: string
  title: string
  required: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()

const root = ref<HTMLElement | null>(null)
const trigger = ref<HTMLButtonElement | null>(null)
const open = ref(false)
const activeIndex = ref(-1)
const listboxId = `column-select-${useId().replace(/[^a-zA-Z0-9_-]/g, '')}`

const selectedOption = computed(
  () => props.options.find((option) => option.value === props.modelValue),
)

const selectedIsDetected = computed(
  () => props.detectedValue !== null && props.modelValue === props.detectedValue,
)

function optionIsDetected(value: string): boolean {
  return props.detectedValue !== null && value === props.detectedValue
}

function optionId(index: number): string {
  return `${listboxId}-option-${index}`
}

function scrollActiveOptionIntoView() {
  void nextTick(() => {
    root.value?.querySelector<HTMLElement>(`#${optionId(activeIndex.value)}`)
      ?.scrollIntoView({ block: 'nearest' })
  })
}

function openMenu() {
  if (open.value) return
  activeIndex.value = Math.max(
    props.options.findIndex((option) => option.value === props.modelValue),
    0,
  )
  open.value = true
  scrollActiveOptionIntoView()
}

function closeMenu() {
  open.value = false
}

function toggleMenu() {
  if (open.value) closeMenu()
  else openMenu()
}

function selectOption(value: string) {
  emit('update:modelValue', value)
  closeMenu()
  trigger.value?.focus()
}

function moveActive(offset: number) {
  openMenu()
  const count = props.options.length
  activeIndex.value = (activeIndex.value + offset + count) % count
  scrollActiveOptionIntoView()
}

function onKeydown(event: KeyboardEvent) {
  if (event.key === 'ArrowDown') {
    event.preventDefault()
    moveActive(1)
  } else if (event.key === 'ArrowUp') {
    event.preventDefault()
    moveActive(-1)
  } else if (event.key === 'Home' || event.key === 'End') {
    event.preventDefault()
    openMenu()
    activeIndex.value = event.key === 'Home' ? 0 : props.options.length - 1
    scrollActiveOptionIntoView()
  } else if (event.key === 'Enter' || event.key === ' ') {
    event.preventDefault()
    if (!open.value) openMenu()
    else selectOption(props.options[activeIndex.value]?.value ?? '')
  } else if (event.key === 'Escape') {
    event.preventDefault()
    closeMenu()
  } else if (event.key === 'Tab') {
    closeMenu()
  }
}

function onDocumentPointerDown(event: PointerEvent) {
  if (!root.value?.contains(event.target as Node)) closeMenu()
}

onMounted(() => document.addEventListener('pointerdown', onDocumentPointerDown))
onBeforeUnmount(() => document.removeEventListener('pointerdown', onDocumentPointerDown))
</script>

<template>
  <div
    ref="root"
    class="column-select"
    :class="{ open }"
    :data-selected-value="modelValue"
  >
    <button
      ref="trigger"
      type="button"
      class="column-select-trigger"
      :class="{ detected: selectedIsDetected }"
      role="combobox"
      aria-haspopup="listbox"
      :aria-label="label"
      :aria-required="required"
      :aria-expanded="open"
      :aria-controls="listboxId"
      :aria-activedescendant="open ? optionId(activeIndex) : undefined"
      :title="title"
      @click="toggleMenu"
      @keydown="onKeydown"
    >
      <span class="column-select-value" :class="{ faint: !selectedOption }">
        {{ selectedOption?.label ?? placeholder }}
      </span>
      <span v-if="selectedIsDetected" class="badge auto">{{ detectedLabel }}</span>
      <span class="column-select-chevron" aria-hidden="true"></span>
    </button>

    <div v-if="open" :id="listboxId" class="column-select-menu" role="listbox">
      <div
        v-for="(option, index) in options"
        :id="optionId(index)"
        :key="option.value"
        role="option"
        :data-value="option.value"
        :aria-selected="option.value === modelValue"
        :class="{
          active: index === activeIndex,
          selected: option.value === modelValue,
        }"
        @pointerenter="activeIndex = index"
        @pointerdown.prevent
        @click="selectOption(option.value)"
      >
        <span>{{ option.label }}</span>
        <span v-if="optionIsDetected(option.value)" class="badge auto">
          {{ detectedLabel }}
        </span>
      </div>
    </div>
  </div>
</template>
