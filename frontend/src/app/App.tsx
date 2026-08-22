import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useEffect } from "react";
import { RouterProvider, createBrowserRouter } from "react-router";

import { router } from "@/app/router";
import { SessionLoading } from "@/app/guards";
import { ErrorBoundary, Toaster } from "@/components/ui";
import { useAuth } from "@/stores/auth";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 15_000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

const browserRouter = createBrowserRouter(router);

function BootGate({ children }: { children: React.ReactNode }) {
  const status = useAuth((state) => state.status);
  const bootstrap = useAuth((state) => state.bootstrap);

  useEffect(() => {
    void bootstrap();
  }, [bootstrap]);

  if (status === "booting") {
    return <SessionLoading />;
  }
  return <>{children}</>;
}

export function App() {
  return (
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <BootGate>
          <RouterProvider router={browserRouter} />
        </BootGate>
        <Toaster />
      </QueryClientProvider>
    </ErrorBoundary>
  );
}
