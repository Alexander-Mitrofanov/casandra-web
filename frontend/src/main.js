import { createApp } from "vue";

import App from "./App.vue";
import { applyFrameBootPolicy } from "./frameGuard.js";
import "./styles.css";

if (applyFrameBootPolicy(window, document)) createApp(App).mount("#root");
