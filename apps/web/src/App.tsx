import { Navigate, Route, Routes } from "react-router-dom";

import Layout from "./components/Layout";
import PrivateRoute, { roleHomePath } from "./components/PrivateRoute";
import SubscriptionGuard from "./components/SubscriptionGuard";
import { useAuth } from "./context/AuthContext";
import AiChatPage from "./pages/AiChatPage";
import AttendancePage from "./pages/AttendancePage";
import AlertsPage from "./pages/AlertsPage";
import BillingPage from "./pages/BillingPage";
import CalculatorPage from "./pages/CalculatorPage";
import CostIntelligencePage from "./pages/CostIntelligencePage";
import CustomersPage from "./pages/CustomersPage";
import DashboardPage from "./pages/DashboardPage";
import FactoryExpensesPage from "./pages/FactoryExpensesPage";
import FactorySheetViewer from "./pages/FactorySheetViewer";
import InvoicesPage from "./pages/InvoicesPage";
import InventoryPage from "./pages/InventoryPage";
import Integrations from "./pages/Integrations";
import LandingPage from "./pages/LandingPage";
import LoginPage from "./pages/LoginPage";
import MachineOnboardingPage from "./pages/MachineOnboardingPage";
import OnboardingPage from "./pages/OnboardingPage";
import OperationsPage from "./pages/OperationsPage";
import DailySequencePage from "./pages/DailySequencePage";
import OutstandingPage from "./pages/OutstandingPage";
import CollectionWarRoomPage from "./pages/CollectionWarRoomPage";
import PaymentCollectionPage from "./pages/PaymentCollectionPage";
import ProductionPage from "./pages/ProductionPage";
import ProfilePage from "./pages/ProfilePage";
import SalesEntryPage from "./pages/SalesEntryPage";
import StaffManagement from "./pages/StaffManagement";
import StorefrontPage from "./pages/StorefrontPage";
import StorefrontSuccessPage from "./pages/StorefrontSuccessPage";
import SubscriptionExpiredPage from "./pages/SubscriptionExpiredPage";
import BriefingHistoryPage from "./pages/BriefingHistoryPage";
import {
  SuperAdminAuditLogsPage,
  SuperAdminBriefingsPage,
  SuperAdminDashboardPage,
  SuperAdminFactoriesPage,
  SuperAdminFactoryDetailPage,
  SuperAdminLoginPage,
  SuperAdminOwnersPage,
  SuperAdminPaymentsPage,
  SuperAdminRoute,
  SuperAdminSubscriptionsPage,
  SuperAdminUsagePage,
} from "./pages/SuperAdminPages";
import UnauthorizedPage from "./pages/UnauthorizedPage";
import PrivacyPolicy from "./components/PrivacyPolicy";
import TermsConditions from "./components/TermsConditions";
import RefundPolicy from "./components/RefundPolicy";

function RoleLanding() {
  const { user } = useAuth();

  if (user && user.role !== "Owner" && user.role !== "Sub-Owner") {
    return <Navigate to={roleHomePath(user.role)} replace />;
  }

  return <DashboardPage />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route path="login" element={<LoginPage />} />
      <Route path="privacy-policy" element={<PrivacyPolicy />} />
      <Route path="terms-conditions" element={<TermsConditions />} />
      <Route path="refund-policy" element={<RefundPolicy />} />
      <Route path="unauthorized" element={<UnauthorizedPage />} />
      <Route path="store/:storeToken" element={<StorefrontPage />} />
      <Route path="store/:storeToken/success" element={<StorefrontSuccessPage />} />
      <Route path="storefront/:storeToken" element={<StorefrontPage />} />
      <Route path="storefront/:storeToken/success" element={<StorefrontSuccessPage />} />
      <Route path="munshi-control-room" element={<SuperAdminLoginPage />} />
      <Route path="munshi-control-room" element={<SuperAdminRoute />}>
        <Route path="dashboard" element={<SuperAdminDashboardPage />} />
        <Route path="factory/:factoryId" element={<FactorySheetViewer />} />
        <Route path="owners" element={<SuperAdminOwnersPage />} />
        <Route path="factories" element={<SuperAdminFactoriesPage />} />
        <Route path="factories/:factoryId" element={<SuperAdminFactoryDetailPage />} />
        <Route path="subscriptions" element={<SuperAdminSubscriptionsPage />} />
        <Route path="payments" element={<SuperAdminPaymentsPage />} />
        <Route path="briefings" element={<SuperAdminBriefingsPage />} />
        <Route path="usage" element={<SuperAdminUsagePage />} />
        <Route path="audit-logs" element={<SuperAdminAuditLogsPage />} />
      </Route>
      <Route
        element={
          <PrivateRoute>
            <SubscriptionGuard>
              <Layout />
            </SubscriptionGuard>
          </PrivateRoute>
        }
      >
        <Route path="billing" element={<BillingPage />} />
        <Route path="plans" element={<BillingPage />} />
        <Route path="subscription-expired" element={<SubscriptionExpiredPage />} />
        <Route path="dashboard" element={<RoleLanding />} />
        <Route
          path="alerts"
          element={
            <PrivateRoute allowedRoles={["Owner", "Sub-Owner"]}>
              <AlertsPage />
            </PrivateRoute>
          }
        />
        <Route path="profile" element={<ProfilePage />} />
        <Route
          path="staff"
          element={
            <PrivateRoute allowedRoles={["Owner", "Sub-Owner"]}>
              <StaffManagement />
            </PrivateRoute>
          }
        />
        <Route
          path="integrations"
          element={
            <PrivateRoute allowedRoles={["Owner", "Sub-Owner"]}>
              <Integrations />
            </PrivateRoute>
          }
        />
        <Route
          path="inventory"
          element={
            <PrivateRoute allowedRoles={["Owner", "Sub-Owner", "Supervisor", "Operator"]}>
              <InventoryPage />
            </PrivateRoute>
          }
        />
        {/* /operations redirected to /daily-sequence to avoid duplicate manual operations sidebar item */}
        <Route
          path="operations"
          element={<Navigate to="/daily-sequence" replace />}
        />
        <Route
          path="daily-sequence"
          element={
            <PrivateRoute allowedRoles={["Owner", "Sub-Owner", "Supervisor", "Operator"]}>
              <DailySequencePage />
            </PrivateRoute>
          }
        />
        <Route
          path="production"
          element={
            <PrivateRoute allowedRoles={["Owner", "Sub-Owner", "Supervisor", "Operator"]}>
              <ProductionPage />
            </PrivateRoute>
          }
        />
        <Route
          path="attendance"
          element={
            <PrivateRoute allowedRoles={["Owner", "Sub-Owner", "Supervisor"]}>
              <AttendancePage />
            </PrivateRoute>
          }
        />
        <Route
          path="sales"
          element={
            <PrivateRoute allowedRoles={["Owner", "Sub-Owner", "Supervisor"]}>
              <SalesEntryPage />
            </PrivateRoute>
          }
        />
        <Route
          path="invoices"
          element={
            <PrivateRoute allowedRoles={["Owner", "Sub-Owner", "Supervisor"]}>
              <InvoicesPage />
            </PrivateRoute>
          }
        />
        <Route
          path="customers"
          element={
            <PrivateRoute allowedRoles={["Owner", "Sub-Owner"]}>
              <CustomersPage />
            </PrivateRoute>
          }
        />
        <Route
          path="outstanding"
          element={
            <PrivateRoute allowedRoles={["Owner", "Sub-Owner"]}>
              <OutstandingPage />
            </PrivateRoute>
          }
        />
        <Route
          path="collection-war-room"
          element={
            <PrivateRoute allowedRoles={["Owner", "Sub-Owner"]}>
              <CollectionWarRoomPage />
            </PrivateRoute>
          }
        />
        <Route
          path="payments"
          element={
            <PrivateRoute allowedRoles={["Owner", "Sub-Owner", "Supervisor"]}>
              <PaymentCollectionPage />
            </PrivateRoute>
          }
        />
        <Route
          path="expenses"
          element={
            <PrivateRoute allowedRoles={["Owner", "Sub-Owner", "Supervisor", "Operator"]}>
              <FactoryExpensesPage />
            </PrivateRoute>
          }
        />
        <Route
          path="onboarding"
          element={
            <PrivateRoute allowedRoles={["Owner", "Sub-Owner"]}>
              <OnboardingPage />
            </PrivateRoute>
          }
        />
        <Route
          path="machine-onboarding"
          element={
            <PrivateRoute allowedRoles={["Owner", "Sub-Owner"]}>
              <MachineOnboardingPage />
            </PrivateRoute>
          }
        />
        <Route
          path="machines"
          element={
            <PrivateRoute allowedRoles={["Owner", "Sub-Owner"]}>
              <MachineOnboardingPage />
            </PrivateRoute>
          }
        />
        <Route
          path="machine-setup"
          element={
            <PrivateRoute allowedRoles={["Owner", "Sub-Owner"]}>
              <MachineOnboardingPage />
            </PrivateRoute>
          }
        />
        <Route
          path="calculator"
          element={
            <PrivateRoute allowedRoles={["Owner", "Sub-Owner"]}>
              <CalculatorPage />
            </PrivateRoute>
          }
        />
        <Route
          path="cost-intelligence"
          element={
            <PrivateRoute allowedRoles={["Owner", "Sub-Owner"]}>
              <CostIntelligencePage />
            </PrivateRoute>
          }
        />
        <Route
          path="briefing-history"
          element={
            <PrivateRoute allowedRoles={["Owner", "Sub-Owner"]}>
              <BriefingHistoryPage />
            </PrivateRoute>
          }
        />
        <Route
          path="ai-supervisor"
          element={
            <PrivateRoute allowedRoles={["Owner", "Sub-Owner", "Supervisor", "Operator"]}>
              <AiChatPage />
            </PrivateRoute>
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
