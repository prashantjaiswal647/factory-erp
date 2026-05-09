import { createContext, useCallback, useContext, useMemo, useState } from "react";

type DataRefreshContextValue = {
  refreshVersion: number;
  triggerDataRefresh: () => void;
};

const DataRefreshContext = createContext<DataRefreshContextValue | null>(null);

export function DataRefreshProvider({ children }: { children: React.ReactNode }) {
  const [refreshVersion, setRefreshVersion] = useState(0);

  const triggerDataRefresh = useCallback(() => {
    setRefreshVersion((currentVersion) => currentVersion + 1);
  }, []);

  const value = useMemo(
    () => ({
      refreshVersion,
      triggerDataRefresh
    }),
    [refreshVersion, triggerDataRefresh]
  );

  return <DataRefreshContext.Provider value={value}>{children}</DataRefreshContext.Provider>;
}

export function useDataRefresh() {
  const context = useContext(DataRefreshContext);

  if (!context) {
    throw new Error("useDataRefresh must be used within DataRefreshProvider");
  }

  return context;
}
