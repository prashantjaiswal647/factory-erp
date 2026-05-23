import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

import App from "./App";
import { AuthProvider } from "./context/AuthContext";
import { DataRefreshProvider } from "./context/DataRefreshContext";
import { UpgradeProvider } from "./context/UpgradeContext";
import "./styles.css";

if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker
      .getRegistrations()
      .then((registrations) => {
        for (const registration of registrations) {
          registration.unregister();
        }
      })
      .then(() => {
        if (!("caches" in window)) return undefined;
        return caches.keys().then((keys) => Promise.all(keys.map((key) => caches.delete(key))));
      })
      .catch((err) => {
        console.error("ServiceWorker cleanup failed:", err);
      });
  });
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <AuthProvider>
      <DataRefreshProvider>
        <BrowserRouter future={{ v7_relativeSplatPath: true, v7_startTransition: true }}>
          <UpgradeProvider>
            <App />
          </UpgradeProvider>
        </BrowserRouter>
      </DataRefreshProvider>
    </AuthProvider>
  </React.StrictMode>
);
