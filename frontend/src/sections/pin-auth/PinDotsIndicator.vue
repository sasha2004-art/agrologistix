<template>
  <div
    class="pin-dots"
    :class="{ 'pin-dots--error': error, 'pin-dots--shake': shaking }"
    role="group"
    aria-label="Введено цифр PIN-кода"
  >
    <span
      v-for="index in 6"
      :key="index"
      class="pin-dot"
      :class="{ 'pin-dot--filled': index <= length }"
      :aria-label="index <= length ? 'Цифра введена' : 'Пусто'"
    />
  </div>
</template>

<script setup lang="ts">
defineProps<{ length: number; error: boolean; shaking: boolean }>()
</script>

<style scoped lang="scss">
.pin-dots {
  display: flex;
  justify-content: center;
  gap: 14px;
}

.pin-dot {
  width: 14px;
  height: 14px;
  border: 2px solid rgba(43, 42, 38, 0.24);
  border-radius: 50%;
  transition:
    border-color 0.15s ease,
    background-color 0.15s ease;
}

.pin-dot--filled {
  border-color: rgb(var(--v-theme-primary));
  background-color: rgb(var(--v-theme-primary));
}

.pin-dots--error .pin-dot {
  border-color: rgb(var(--v-theme-error));
  background-color: rgb(var(--v-theme-error));
}

.pin-dots--shake {
  animation: shake 300ms ease both;
}

@keyframes shake {
  0%,
  100% {
    transform: translateX(0);
  }
  20%,
  60% {
    transform: translateX(-6px);
  }
  40%,
  80% {
    transform: translateX(6px);
  }
}

@media (prefers-reduced-motion: reduce) {
  .pin-dots--shake {
    animation: none;
  }
}
</style>
