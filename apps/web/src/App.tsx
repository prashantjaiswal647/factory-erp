import { Navigate, Route, Routes } from "react-router-dom";

import Layout from "./components/Layout";
import PrivateRoute from "./components/PrivateRoute";
import { useAuth } from "./context/AuthContext";
import AiChatPage from "./pages/AiChatPage";
import CustomersPage from "./pages/CustomersPage";
import CustomerStorefrontPage from "./pages/CustomerStorefrontPage";
import DashboardPage from "./pages/DashboardPage";
import InventoryPage from "./pages/InventoryPage";
import LoginPage from "./pages/LoginPage";
import ProductionPage from "./pages/ProductionPage";
import StorefrontSuccessPage from "./pages/StorefrontSuccessPage";

function RoleLanding() {
  const { user } = useAuth();

  if (user?.role === "Operator") {
    return <Navigate to="/production" replace />;
  }

  return <DashboardPage />;
}

export default function App() {
  return (
    <Routes>
      <Route path="login" element={<LoginPage />} />
      <Route path="store/:storeToken" element={<CustomerStorefrontPage />} />
      <Route path="store/:storeToken/success" element={<StorefrontSuccessPage />} />
      <Route
        element={
          <PrivateRoute>
            <Layout />
          </PrivateRoute>
        }
      >
        <Route index element={<RoleLanding />} />
        <Route
          path="inventory"
          element={
            <PrivateRoute allowedRoles={["Owner"]}>
              <InventoryPage />
            </PrivateRoute>
          }
        />
        <Route path="production" element={<ProductionPage />} />
        <Route
          path="customers"
          element={
            <PrivateRoute allowedRoles={["Owner"]}>
              <CustomersPage />
            </PrivateRoute>
          }
        />
        <Route path="ai-supervisor" element={<AiChatPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
