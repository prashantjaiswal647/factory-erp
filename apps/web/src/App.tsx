import { Navigate, Route, Routes } from "react-router-dom";

import Layout from "./components/Layout";
import PrivateRoute, { roleHomePath } from "./components/PrivateRoute";
import { useAuth } from "./context/AuthContext";
import AiChatPage from "./pages/AiChatPage";
import CalculatorPage from "./pages/CalculatorPage";
import CustomersPage from "./pages/CustomersPage";
import DashboardPage from "./pages/DashboardPage";
import InventoryPage from "./pages/InventoryPage";
import LandingPage from "./pages/LandingPage";
import LoginPage from "./pages/LoginPage";
import OnboardingPage from "./pages/OnboardingPage";
import OutstandingPage from "./pages/OutstandingPage";
import PaymentCollectionPage from "./pages/PaymentCollectionPage";
import ProductionPage from "./pages/ProductionPage";
import SalesEntryPage from "./pages/SalesEntryPage";
import StorefrontPage from "./pages/StorefrontPage";
import StorefrontSuccessPage from "./pages/StorefrontSuccessPage";
import UnauthorizedPage from "./pages/UnauthorizedPage";

function RoleLanding() {
  const { user } = useAuth();

  if (user && user.role !== "Owner") {
    return <Navigate to={roleHomePath(user.role)} replace />;
  }

  return <DashboardPage />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route path="login" element={<LoginPage />} />
      <Route path="unauthorized" element={<UnauthorizedPage />} />
      <Route path="store/:storeToken" element={<StorefrontPage />} />
      <Route path="store/:storeToken/success" element={<StorefrontSuccessPage />} />
      <Route path="storefront/:storeToken" element={<StorefrontPage />} />
      <Route path="storefront/:storeToken/success" element={<StorefrontSuccessPage />} />
      <Route
        element={
          <PrivateRoute>
            <Layout />
          </PrivateRoute>
        }
      >
        <Route path="dashboard" element={<RoleLanding />} />
        <Route
          path="inventory"
          element={
            <PrivateRoute allowedRoles={["Owner", "Supervisor", "Operator"]}>
              <InventoryPage />
            </PrivateRoute>
          }
        />
        <Route
          path="production"
          element={
            <PrivateRoute allowedRoles={["Owner", "Supervisor", "Operator"]}>
              <ProductionPage />
            </PrivateRoute>
          }
        />
        <Route
          path="sales"
          element={
            <PrivateRoute allowedRoles={["Owner", "Supervisor"]}>
              <SalesEntryPage />
            </PrivateRoute>
          }
        />
        <Route
          path="customers"
          element={
            <PrivateRoute allowedRoles={["Owner"]}>
              <CustomersPage />
            </PrivateRoute>
          }
        />
        <Route
          path="outstanding"
          element={
            <PrivateRoute allowedRoles={["Owner"]}>
              <OutstandingPage />
            </PrivateRoute>
          }
        />
        <Route
          path="payments"
          element={
            <PrivateRoute allowedRoles={["Owner", "Supervisor"]}>
              <PaymentCollectionPage />
            </PrivateRoute>
          }
        />
        <Route
          path="onboarding"
          element={
            <PrivateRoute allowedRoles={["Owner"]}>
              <OnboardingPage />
            </PrivateRoute>
          }
        />
        <Route
          path="calculator"
          element={
            <PrivateRoute allowedRoles={["Owner"]}>
              <CalculatorPage />
            </PrivateRoute>
          }
        />
        <Route
          path="ai-supervisor"
          element={
            <PrivateRoute allowedRoles={["Owner", "Supervisor", "Operator"]}>
              <AiChatPage />
            </PrivateRoute>
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
