import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider } from "./context/AuthContext";
import { AccountLayout, Layout, RequireAuth } from "./layout";
import { LoginPage, RegisterPage } from "./pages/Auth";
import { HomePage } from "./pages/Home";
import { ProductPage } from "./pages/Product";
import { CartPage } from "./pages/Cart";
import { OrdersPage, OrderDetailPage } from "./pages/Orders";
import {
  AddressesPage,
  ProfilePage,
  SessionsPage,
  SettingsPage,
} from "./pages/Account";
import { Button, EmptyState } from "./components/ui";

function NotFound() {
  return (
    <EmptyState
      icon="🧭"
      title="Page not found"
      subtitle="The page you were looking for doesn't exist."
      action={
        <a href="/" className="no-underline">
          <Button>Back to home</Button>
        </a>
      }
    />
  );
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Layout>
          <Routes>
            <Route path="/" element={<HomePage />} />
            <Route path="/product/:id" element={<ProductPage />} />
            <Route path="/login" element={<LoginPage />} />
            <Route path="/register" element={<RegisterPage />} />

            <Route
              path="/cart"
              element={
                <RequireAuth>
                  <CartPage />
                </RequireAuth>
              }
            />
            <Route
              path="/orders"
              element={
                <RequireAuth>
                  <OrdersPage />
                </RequireAuth>
              }
            />
            <Route
              path="/orders/:id"
              element={
                <RequireAuth>
                  <OrderDetailPage />
                </RequireAuth>
              }
            />
            <Route
              path="/account"
              element={
                <RequireAuth>
                  <AccountLayout />
                </RequireAuth>
              }
            >
              <Route index element={<ProfilePage />} />
              <Route path="addresses" element={<AddressesPage />} />
              <Route path="sessions" element={<SessionsPage />} />
              <Route path="settings" element={<SettingsPage />} />
            </Route>

            <Route path="/404" element={<NotFound />} />
            <Route path="*" element={<Navigate to="/404" replace />} />
          </Routes>
        </Layout>
      </BrowserRouter>
    </AuthProvider>
  );
}
