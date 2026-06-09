import { createApp } from "vue";
import { createPinia } from "pinia";
import { VueQueryPlugin } from "@tanstack/vue-query";
import App from "./App.vue";
import { queryClient } from "./lib/queryClient";
import "./styles.css";

const app = createApp(App);
app.use(createPinia());
app.use(VueQueryPlugin, { queryClient });
app.mount("#app");
