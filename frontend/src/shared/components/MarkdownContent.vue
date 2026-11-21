<script setup lang="ts">
defineProps<{ sanitizedHtml: string }>()
</script>

<template>
  <div class="job-markdown" v-html="sanitizedHtml" />
</template>

<style scoped>
.job-markdown {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  overflow-wrap: anywhere;
}

.job-markdown :deep(:is(h1, h2, h3, h4, h5, h6)) {
  font-weight: 600;
  color: var(--ink);
}

.job-markdown :deep(:is(h1, h2, h3, h4, h5, h6):not(:first-child)) {
  margin-top: var(--space-1);
}

.job-markdown :deep(p:empty) {
  display: none;
}

.job-markdown :deep(:is(strong, b)) {
  font-weight: 600;
}

.job-markdown :deep(:is(ul, ol)) {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  padding-left: var(--space-6);
}

.job-markdown :deep(ul) {
  list-style: disc;
}

.job-markdown :deep(ol) {
  list-style: decimal;
}

.job-markdown :deep(li::marker) {
  color: var(--ink-muted);
}

.job-markdown :deep(li > :is(ul, ol, p + p)) {
  margin-top: var(--space-1);
}

.job-markdown :deep(a[href]) {
  color: var(--link);
  text-decoration: underline;
  text-underline-offset: 2px;
  border-radius: 2px;
  transition: color 150ms ease-out;
}

.job-markdown :deep(a[href]:hover) {
  color: var(--accent-hover);
}

.job-markdown :deep(a[href]:focus-visible) {
  outline: none;
  box-shadow: var(--focus-ring);
}

.job-markdown :deep(code) {
  padding: 0 var(--space-1);
  border-radius: 4px;
  background: var(--surface-subtle);
  font-family: var(--font-mono, ui-monospace, monospace);
}

.job-markdown :deep(pre) {
  overflow-x: auto;
  padding: var(--space-3);
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--surface-subtle);
}

.job-markdown :deep(pre code) {
  padding: 0;
  background: none;
}

.job-markdown :deep(blockquote) {
  padding-left: var(--space-3);
  border-left: 2px solid var(--line-strong);
  color: var(--ink-muted);
}
</style>
