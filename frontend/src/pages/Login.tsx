import { useState } from "react";
import { t } from "../i18n";
import { supabase } from "../lib/supabaseClient";
import { useUiLocale } from "../lib/useLocale";

/** action-plan.md §10: users are invited by an admin, not self-registered
 * (see supabase/config.toml, enable_signup = false) — this is a magic-link
 * sign-in only. */
export function Login() {
  const locale = useUiLocale();
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    const { error: signInError } = await supabase.auth.signInWithOtp({ email });
    if (signInError) setError(signInError.message);
    else setSent(true);
  }

  if (sent) {
    return <p>Check your email for a sign-in link.</p>;
  }

  return (
    <form onSubmit={handleSubmit}>
      <h1>{t(locale, "login.title")}</h1>
      <label>
        {t(locale, "login.email")}
        <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
      </label>
      {error && <p role="alert">{error}</p>}
      <button type="submit">{t(locale, "login.submit")}</button>
    </form>
  );
}
