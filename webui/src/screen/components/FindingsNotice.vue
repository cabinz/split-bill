<script setup lang="ts">
import { translateBackendMessage, useI18n } from '../../presentation/i18n'
import type { Finding } from '../../presentation/types'

const props = defineProps<{
  kind: 'error' | 'warn'
  title: string
  findings: Finding[]
}>()

const { t } = useI18n()

function moreLabel(): string {
  return t(
    props.kind === 'error' ? 'finding.moreErrors' : 'finding.moreWarnings',
    { count: props.findings.length - 1 },
  )
}
</script>

<template>
  <div class="notice findings-notice" :class="kind">
    <strong>{{ title }}</strong>
    <ul>
      <li v-if="findings[0]">
        <template v-if="findings[0].row">
          {{ t('finding.row', { row: findings[0].row }) }}
        </template>
        <template v-else-if="findings[0].column">
          {{ t('finding.column', { column: findings[0].column }) }}
        </template>
        {{ translateBackendMessage(findings[0].message) }}
      </li>
    </ul>
    <details v-if="findings.length > 1" class="finding-more">
      <summary>{{ moreLabel() }}</summary>
      <ul>
        <li v-for="(finding, index) in findings.slice(1)" :key="index">
          <template v-if="finding.row">
            {{ t('finding.row', { row: finding.row }) }}
          </template>
          <template v-else-if="finding.column">
            {{ t('finding.column', { column: finding.column }) }}
          </template>
          {{ translateBackendMessage(finding.message) }}
        </li>
      </ul>
    </details>
  </div>
</template>
