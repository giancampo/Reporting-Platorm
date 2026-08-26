import { useState } from "react";
import { t } from "../i18n";
import { useUiLocale } from "../lib/useLocale";

/** action-plan.md §11: "The analyst's edited version supersedes the
 * generated one and is kept in history." This component is the editing
 * surface; persistence (a new `comments` row/version) is the caller's job. */
export function CommentEditor(props: {
  generatedText: string | null;
  editedText: string | null;
  status: "draft" | "approved";
  onSave: (text: string) => void;
  onApprove: () => void;
}) {
  const locale = useUiLocale();
  const [draft, setDraft] = useState(props.editedText ?? props.generatedText ?? "");

  return (
    <div>
      <span>{t(locale, `comment.status.${props.status}`)}</span>
      <textarea value={draft} onChange={(e) => setDraft(e.target.value)} rows={4} />
      <button type="button" onClick={() => props.onSave(draft)}>
        {t(locale, "comment.edit")}
      </button>
      <button type="button" onClick={props.onApprove} disabled={props.status === "approved"}>
        {t(locale, "comment.status.approved")}
      </button>
    </div>
  );
}
