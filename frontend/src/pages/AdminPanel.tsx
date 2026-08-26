import { useEffect, useState } from "react";
import { t } from "../i18n";
import { supabase } from "../lib/supabaseClient";
import { useUiLocale } from "../lib/useLocale";

interface ProjectRow {
  id: string;
  slug: string;
  display_name: string;
  report_language: string;
  timezone: string;
}

/** action-plan.md §10: "admin panel to create projects and invite users."
 * Creating a project/user is a Supabase insert, protected by the RLS
 * policies in supabase/migrations/0002_rls_policies.sql — this page has no
 * privilege logic of its own. */
export function AdminPanel() {
  const locale = useUiLocale();
  const [projects, setProjects] = useState<ProjectRow[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    supabase
      .from("projects")
      .select("id, slug, display_name, report_language, timezone")
      .then(({ data, error: fetchError }) => {
        if (fetchError) setError(fetchError.message);
        else setProjects(data ?? []);
      });
  }, []);

  return (
    <section>
      <h1>{t(locale, "admin.projects.title")}</h1>
      {error && <p role="alert">{error}</p>}
      <table>
        <thead>
          <tr>
            <th>Slug</th>
            <th>Name</th>
            <th>Report language</th>
            <th>Timezone</th>
          </tr>
        </thead>
        <tbody>
          {projects.map((project) => (
            <tr key={project.id}>
              <td>{project.slug}</td>
              <td>{project.display_name}</td>
              <td>{project.report_language}</td>
              <td>{project.timezone}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
