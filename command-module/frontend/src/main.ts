import { createApp } from "vue";
import { createRouter, createWebHistory } from "vue-router";
import App from "./App.vue";
import "./index.css";

import Dashboard    from "./pages/Dashboard.vue";
import Events       from "./pages/Events.vue";
import Persons      from "./pages/Persons.vue";
import Settings     from "./pages/Settings.vue";
import CameraDetail from "./pages/CameraDetail.vue";
import AlertDetail  from "./pages/AlertDetail.vue";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/",                             component: Dashboard    },
    { path: "/events",                       component: Events       },
    { path: "/persons",                      component: Persons      },
    { path: "/settings",                     component: Settings     },
    { path: "/cameras/:cameraId",            component: CameraDetail },
    { path: "/events/:eventId",              component: AlertDetail  },
  ],
});

createApp(App).use(router).mount("#app");
