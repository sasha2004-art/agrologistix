<template>
  <div class="notification-host" aria-live="polite">
    <v-alert
      v-for="item in notifications.items"
      :key="item.id"
      :type="item.type"
      variant="tonal"
      density="comfortable"
      closable
      class="notification-item"
      :role="item.type === 'error' ? 'alert' : 'status'"
      @click:close="notifications.dismiss(item.id)"
    >
      {{ item.text }}
    </v-alert>
  </div>
</template>

<script setup lang="ts">
import { useNotificationStore } from '@/shared/stores/useNotificationStore'

const notifications = useNotificationStore()
</script>

<style scoped lang="scss">
.notification-host {
  position: fixed;
  top: 76px;
  right: 16px;
  z-index: 3000;
  display: grid;
  gap: 8px;
  width: min(360px, calc(100vw - 32px));
  pointer-events: none;
}

.notification-item {
  pointer-events: auto;
  border: var(--neu-border) !important;
  box-shadow: var(--neu-lift-sm);
}

@media (max-width: 599px) {
  .notification-host {
    top: 70px;
    right: 8px;
    width: calc(100vw - 16px);
  }
}
</style>
