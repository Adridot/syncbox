import { createApp } from "vue";
import { createPinia } from "pinia";
import { VueQueryPlugin } from "@tanstack/vue-query";
import App from "./App.vue";
import { i18n } from "./i18n";
import { queryClient } from "./lib/queryClient";
import "./styles.css";

const app = createApp(App);
app.use(createPinia());
app.use(i18n);
app.use(VueQueryPlugin, { queryClient });
app.mount("#app");
