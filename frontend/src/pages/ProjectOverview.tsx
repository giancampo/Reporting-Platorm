import { useEffect, useState } from "react";
import { t } from "../i18n";
import { supabase } from "../lib/supabaseClient";
import { useUiLocale } from "../lib/useLocale";

interface ProjectSummary {
  id: string;
  slug: string;
  display_name: string;
}

/** action-plan.md §10 / §14 Phase 6: "cross-account overview with KPIs for
 * every project." KPI values themselves come from each project's GCS
 * documents via the signing service (same path as ReportPage) — this page
 * lists the projects the current user can see (RLS-scoped) and lets them
 * drill in. */
export function ProjectOverview(props: { onSelectProject: (projectId: string) => void }) {
  const locale = useUiLocale();
  const [projects, setProjects] = useState<ProjectSummary[]>([]);

  useEffect(() => {
    supabase
      .from("projects")
      .select("id, slug, display_name")
      .then(({ data }) => setProjects(data ?? []));
  }, []);

  return (
    <section>
      <h1>{t(locale, "nav.overview")}</h1>
      <ul>
        {projects.map((project) => (
          <li key={project.id}>
            <button type="button" onClick={() => props.onSelectProject(project.id)}>
              {project.display_name}
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
