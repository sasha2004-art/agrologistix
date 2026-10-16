<template>
  <main class="landing-page">
    <VideoBackdrop />
    <v-container class="landing-shell" max-width="1280">
      <header class="landing-header">
        <RouterLink class="brand-lockup" to="/" aria-label="AgroLogistix, главная">
          <span class="brand-mark"><v-icon icon="mdi-leaf" size="20" /></span>
          <span>AGROLOGISTIX <i>//</i> КАЛУГА-ОБНИНСК</span>
        </RouterLink>
        <span class="region-tag">ОБНИНСК-СЕВЕРНЫЙ <i /> ДЕТЧИНО-АГРО</span>
      </header>

      <section class="hero-content" aria-labelledby="hero-title">
        <div class="hero-copy">
          <h1 id="hero-title">Свежий урожай.<br /><em>Точный маршрут.</em></h1>
          <p class="hero-description">
            AgroLogistix объединяет склады, автопарк и B2B-заказы Калужской области, чтобы
            скоропортящийся урожай доезжал вовремя и сохранял ценность.
          </p>
          <div class="hero-actions">
            <v-btn to="/login" color="primary" size="large" append-icon="mdi-arrow-up-right">
              Открыть терминал логиста
            </v-btn>
            <span class="hero-note"><v-icon icon="mdi-map-marker-outline" size="16" /> Обнинск и область</span>
          </div>
        </div>

        <aside class="dispatch-card liquid-glass" aria-label="Факторы оптимизации">
          <div class="card-topline"><span>ПЛАН ПОСТАВОК</span><span class="status-pill">СИСТЕМА ГОТОВА</span></div>
          <div class="route-visual">
            <div class="route-stops">
              <span class="stop-dot warehouse-dot"></span>
              <span class="route-line"></span>
              <span class="stop-dot client-dot"></span>
            </div>
            <div class="route-labels"><span>СКЛАД · ОБНИНСК</span><span>B2B · КАЛУГА</span></div>
            <div class="route-metrics"><strong>Свежесть</strong><span class="mono">E[Freshness] <b>94.8%</b></span></div>
          </div>
          <div class="factor-list">
            <div><v-icon icon="mdi-snowflake" /><span>Терморежим</span><strong>Рефрижератор</strong></div>
            <div><v-icon icon="mdi-weather-cloudy" /><span>Погода</span><strong>Учтена в TCO</strong></div>
            <div><v-icon icon="mdi-road-variant" /><span>Доступность</span><strong>Покрытие дорог</strong></div>
          </div>
          <div class="card-foot"><span>ЕДИНЫЙ РАСЧЁТ РЕЙСА</span><span class="mono">TCO ↗</span></div>
        </aside>
      </section>

      <footer class="landing-footer liquid-glass">
        <v-row class="footer-top" align="start">
          <v-col cols="12" md="5" class="footer-brand">
            <div class="footer-logo"><v-icon icon="mdi-leaf" size="21" /><span>AgroLogistix</span></div>
            <p>Био-логистика скоропортящегося урожая для Калужской области.</p>
          </v-col>
          <v-col cols="12" md="7">
            <v-row>
              <v-col cols="6" sm="4">
                <h2>ПЛАТФОРМА</h2>
                <a href="#optimization">Оптимизация маршрутов</a>
                <a href="#tco">Экономика TCO</a>
                <a href="#freshness">Свежесть урожая</a>
              </v-col>
              <v-col cols="6" sm="4">
                <h2>РЕГИОН</h2>
                <a href="#obninsk">Обнинск</a>
                <a href="#kaluga">Калужская область</a>
                <a href="#warehouses">Складская сеть</a>
              </v-col>
              <v-col cols="12" sm="4">
                <h2>ТЕРМИНАЛ</h2>
                <RouterLink to="/login">Вход для логистов</RouterLink>
                <a href="mailto:logistics@agrologistix.local">Связаться с командой</a>
              </v-col>
            </v-row>
          </v-col>
        </v-row>
        <div class="footer-bottom">
          <span>© AGROLOGISTIX · КАЛУГА—ОБНИНСК</span>
          <span>Урожай в движении. Ценность сохранена.</span>
          <RouterLink to="/login">ТЕРМИНАЛ <v-icon icon="mdi-arrow-up-right" size="14" /></RouterLink>
        </div>
      </footer>
    </v-container>
  </main>
</template>

<script setup lang="ts">
import { RouterLink } from 'vue-router'
import VideoBackdrop from '@/shared/components/VideoBackdrop.vue'
</script>

<style scoped lang="scss">
.landing-page { position: relative; z-index: 1; min-height: 100vh; color: #f8fafc; }
.landing-shell { position: relative; z-index: 1; min-height: 100vh; display: flex; flex-direction: column; padding: 28px 34px 24px; }
.landing-header { display: flex; justify-content: space-between; align-items: center; min-height: 42px; }
.brand-lockup, .footer-logo { display: inline-flex; align-items: center; gap: 10px; color: #f8fafc; text-decoration: none; font-size: 15px; font-weight: 700; letter-spacing: .06em; }
.brand-mark { display: grid; place-items: center; width: 34px; height: 34px; color: #061b16; background: #10b981; border-radius: 10px; }
.brand-lockup i { padding: 0 2px; color: #34d399; font-style: normal; }
.region-tag { color: rgba(226, 232, 240, .66); font: 10px var(--font-mono); letter-spacing: .12em; }
.region-tag i { display: inline-block; width: 4px; height: 4px; margin: 0 8px 2px; border-radius: 50%; background: #10b981; }
.hero-content { flex: 1; display: grid; grid-template-columns: minmax(0, 1.12fr) minmax(330px, .72fr); align-items: center; gap: 9%; padding: 46px 3% 56px; }
.hero-copy { max-width: 680px; }
h1 { margin: 0; font-size: clamp(46px, 5.1vw, 72px); font-weight: 500; line-height: 1.02; letter-spacing: -.035em; }
h1 em { color: #6ee7b7; font-style: normal; }
.hero-description { max-width: 510px; margin: 24px 0 29px; color: #d1d9e3; font-size: 16px; line-height: 1.7; }
.hero-actions { display: flex; align-items: center; gap: 21px; flex-wrap: wrap; }
.hero-note { display: inline-flex; gap: 6px; align-items: center; color: #cbd5e1; font-size: 12px; }
.dispatch-card { max-width: 390px; width: 100%; justify-self: center; padding: 22px; border-radius: 18px; background-color: rgba(15, 23, 42, .62); }
.card-topline, .card-foot { display: flex; align-items: center; justify-content: space-between; color: rgba(226,232,240,.58); font: 9px var(--font-mono); letter-spacing: .09em; }
.status-pill { color: #a7f3d0; padding: 6px 8px; border-radius: 5px; background: rgba(16,185,129,.13); }
.route-visual { margin: 28px 0 21px; padding: 17px 14px 12px; border-radius: 10px; background: rgba(8,17,31,.44); }
.route-stops { display: flex; align-items: center; padding: 0 7px; }
.stop-dot { flex: none; width: 10px; height: 10px; border: 2px solid #10b981; border-radius: 50%; background: #0f172a; }
.client-dot { border-color: #38bdf8; }
.route-line { height: 1px; flex: 1; background: linear-gradient(90deg, #10b981, #38bdf8); }
.route-labels { display: flex; justify-content: space-between; margin-top: 10px; color: #94a3b8; font: 8px var(--font-mono); }
.route-metrics { display: flex; justify-content: space-between; align-items: center; margin-top: 21px; padding-top: 13px; border-top: 1px solid rgba(226,232,240,.1); color: #dbe4ee; font-size: 12px; }
.route-metrics .mono { color: #94a3b8; font-size: 9px; }.route-metrics b { color: #6ee7b7; font-size: 12px; }
.factor-list { display: grid; gap: 12px; padding: 0 2px 18px; }
.factor-list > div { display: grid; grid-template-columns: 22px 1fr auto; align-items: center; gap: 8px; color: #94a3b8; font-size: 11px; }
.factor-list .v-icon { color: #38bdf8; font-size: 16px; }
.factor-list strong { color: #e2e8f0; font-size: 10px; font-weight: 500; }
.card-foot { padding-top: 13px; border-top: 1px solid rgba(226,232,240,.12); }
.card-foot .mono { color: #a7f3d0; }
.landing-footer { padding: 22px 27px 0; border-radius: 16px 16px 0 0; background: rgba(15, 23, 42, .68); }
.footer-top { padding-bottom: 17px; }
.footer-logo { font-size: 16px; letter-spacing: 0; }.footer-logo .v-icon { color: #34d399; }
.footer-brand p { max-width: 250px; margin: 12px 0 0; color: #cbd5e1; font-size: 12px; line-height: 1.6; }
.landing-footer h2 { margin: 1px 0 12px; color: #f8fafc; font: 10px var(--font-mono); letter-spacing: .09em; }
.landing-footer a { display: block; width: fit-content; margin: 0 0 9px; color: #b5c1d0; text-decoration: none; font-size: 11px; transition: color .18s ease; }
.landing-footer a:hover { color: #6ee7b7; }
.footer-bottom { display: flex; justify-content: space-between; align-items: center; gap: 16px; min-height: 43px; border-top: 1px solid rgba(255,255,255,.1); color: #94a3b8; font: 8px var(--font-mono); letter-spacing: .04em; }
.footer-bottom a { display: inline-flex; align-items: center; margin: 0; color: #a7f3d0; }
@media (max-width: 900px) { .hero-content { gap: 5%; padding-inline: 1%; }.landing-shell { padding-inline: 24px; } }
@media (max-width: 680px) {
  .landing-shell { padding: 18px 16px 0; }.region-tag { font-size: 8px; }
  .hero-content { grid-template-columns: 1fr; gap: 31px; padding: 68px 2% 34px; }
  h1 { font-size: clamp(43px, 12vw, 62px); }.hero-description { font-size: 14px; }
  .dispatch-card { max-width: none; }.landing-footer { padding: 19px 17px 0; }
  .footer-bottom { flex-wrap: wrap; justify-content: space-between; padding: 12px 0; }.footer-bottom > span:nth-child(2) { display: none; }
}
@media (prefers-reduced-motion: reduce) { *, *::before, *::after { scroll-behavior: auto !important; transition-duration: .01ms !important; } }
</style>
