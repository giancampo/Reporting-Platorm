import { useEffect, useState } from "react";
import type { Session } from "@supabase/supabase-js";
import { AdminPanel } from "./pages/AdminPanel";
import { DataPrivacyPage } from "./pages/DataPrivacyPage";
import { Login } from "./pages/Login";
import { ProjectOverview } from "./pages/ProjectOverview";
import { supabase } from "./lib/supabaseClient";
import { t } from "./i18n";
import type { SupportedLocale } from "./i18n";
import { ReportLocaleContext, UiLocaleContext } from "./lib/useLocale";

type Route = "overview" | "admin" | "data-privacy";

/** Top-level shell. Routing is intentionally minimal (no report_defs-driven
 * pages wired in yet beyond ReportPage's own component) — the point of this
 * scaffold is the config-driven pieces underneath it, not a polished nav. */
export function App() {
  const [session, setSession] = useState<Session | null>(null);
  const [route, setRoute] = useState<Route>("overview");
  const [uiLocale] = useState<SupportedLocale>("en");
  const [reportLocale] = useState<SupportedLocale>("en"); // set per-project once a project is selected

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => setSession(data.session));
    const { data: subscription } = supabase.auth.onAuthStateChange((_event, newSession) => {
      setSession(newSession);
    });
    return () => subscription.subscription.unsubscribe();
  }, []);

  if (!session) {
    return (
      <UiLocaleContext.Provider value={uiLocale}>
        <Login />
      </UiLocaleContext.Provider>
    );
  }

  return (
    <UiLocaleContext.Provider value={uiLocale}>
      <ReportLocaleContext.Provider value={reportLocale}>
        <nav>
          <button type="button" onClick={() => setRoute("overview")}>
            {t(uiLocale, "nav.overview")}
          </button>
          <button type="button" onClick={() => setRoute("admin")}>
            {t(uiLocale, "nav.admin")}
          </button>
          <button type="button" onClick={() => setRoute("data-privacy")}>
            {t(uiLocale, "nav.dataPrivacy")}
          </button>
          <button type="button" onClick={() => supabase.auth.signOut()}>
            {t(uiLocale, "nav.logout")}
          </button>
        </nav>
        <main>
          {route === "overview" && <ProjectOverview onSelectProject={() => setRoute("overview")} />}
          {route === "admin" && <AdminPanel />}
          {route === "data-privacy" && <DataPrivacyPage />}
        </main>
      </ReportLocaleContext.Provider>
    </UiLocaleContext.Provider>
  );
}
