import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

import App from "./App";
import { AuthProvider } from "./context/AuthContext";
import { DataRefreshProvider } from "./context/DataRefreshContext";
import { UpgradeProvider } from "./context/UpgradeContext";
import "./styles.css";

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
