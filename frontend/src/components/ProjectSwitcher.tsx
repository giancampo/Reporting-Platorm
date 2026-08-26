import { t } from "../i18n";
import { useUiLocale } from "../lib/useLocale";

export interface ProjectOption {
  id: string;
  slug: string;
  displayName: string;
}

/** action-plan.md §10: "project switcher always visible for analysts." */
export function ProjectSwitcher(props: {
  projects: ProjectOption[];
  selectedProjectId: string | null;
  onSelect: (projectId: string) => void;
}) {
  const locale = useUiLocale();
  return (
    <label>
      {t(locale, "projectSwitcher.label")}
      <select
        value={props.selectedProjectId ?? ""}
        onChange={(e) => props.onSelect(e.target.value)}
      >
        {props.projects.map((project) => (
          <option key={project.id} value={project.id}>
            {project.displayName}
          </option>
        ))}
      </select>
    </label>
  );
}
