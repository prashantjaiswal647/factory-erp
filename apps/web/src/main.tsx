import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

import App from "./App";
import { AuthProvider } from "./context/AuthContext";
import { DataRefreshProvider } from "./context/DataRefreshContext";
import "./styles.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <AuthProvider>
      <DataRefreshProvider>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </DataRefreshProvider>
    </AuthProvider>
  </React.StrictMode>
);
