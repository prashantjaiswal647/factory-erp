export const FACTORY_HEALTH_RISK_ROUTES: Record<string, string> = {
  Production: "/production",
  Attendance: "/attendance",
  Collections: "/outstanding",
  Inventory: "/inventory",
  Cost: "/cost-intelligence",
};

export function factoryHealthRiskRoute(risk: string) {
  return FACTORY_HEALTH_RISK_ROUTES[risk] || "/dashboard";
}
