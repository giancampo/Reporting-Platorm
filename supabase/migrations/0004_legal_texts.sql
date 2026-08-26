-- Legal/disclaimer text as configuration, not code (action-plan.md §16:
-- "Both texts come from a configuration entry, not from code, so updating
-- them requires no deploy"). Consumed by the frontend's Data & Privacy page
-- and by the PDF footer.

create table legal_texts (
  key         text primary key,
  content     jsonb not null,     -- {"en": "...", "it": "..."} — en mandatory (§5)
  updated_at  timestamptz not null default now()
);

alter table legal_texts enable row level security;

create policy legal_texts_select_all on legal_texts for select using (true);
create policy legal_texts_admin_write on legal_texts for all
  using (is_global_admin()) with check (is_global_admin());

create trigger set_legal_texts_updated_at
  before update on legal_texts
  for each row execute function set_updated_at();

insert into legal_texts (key, content) values (
  'data_residency_disclaimer',
  '{
    "en": "**Data residency and provider jurisdiction**\n\nAll data handled by this tool is stored exclusively within the European Union:\n- reporting data on Cloudflare R2, bucket created with the `eu` jurisdiction (pinned to EU member-state data centres, no replication to North America);\n- users, configuration and comments on Supabase, region `eu-central-1` (Frankfurt);\n- ETL processing on Google Cloud Run, region `europe-west1`;\n- credentials in Google Secret Manager with EU-region replication.\n\nStored reporting data consists of statistical aggregates (sessions by channel, revenue by country, products by category) and contains no individual identifiers, client IDs, user IDs or user-level events. The only personal data processed by the tool are the email addresses of authorised users.\n\nKnown limitation. The infrastructure providers used — Cloudflare, Inc. and Google LLC — are US-incorporated companies and therefore subject to the CLOUD Act, even when data physically resides in the European Union. The tool therefore satisfies a data residency requirement, but not a contractual requirement for processing by a processor established exclusively within the EU. Should a client impose that constraint, the storage and compute components must be migrated to European providers (for example Scaleway, OVHcloud, Hetzner, Exoscale), with an impact on operating costs.\n\nObligations of the tool operator: execute DPAs with the providers, maintain an up-to-date sub-processor list, verify the legal bases for processing.\n\nThis text is informational and does not constitute legal advice. Have it reviewed by legal counsel before using it in a contractual context or reproducing it in a client-facing privacy notice.",
    "it": "**Residenza dei dati e giurisdizione del fornitore**\n\nTutti i dati trattati da questo strumento sono archiviati esclusivamente all''interno dell''Unione Europea:\n- dati di reporting su Cloudflare R2, bucket con jurisdiction `eu` (pinning ai data center di stati membri UE, nessuna replica verso il Nord America);\n- utenti, configurazioni e commenti su Supabase, region `eu-central-1` (Francoforte);\n- elaborazione ETL su Google Cloud Run, region `europe-west1`;\n- credenziali su Google Secret Manager con replica in region UE.\n\nI dati di reporting archiviati sono aggregati statistici (sessioni per canale, ricavi per paese, prodotti per categoria) e non contengono identificatori individuali, client ID, user ID o eventi a livello di singolo utente. Gli unici dati personali trattati dallo strumento sono gli indirizzi email degli utenti abilitati all''accesso.\n\nLimite noto. I fornitori infrastrutturali impiegati — Cloudflare, Inc. e Google LLC — sono società di diritto statunitense e in quanto tali soggette al CLOUD Act, anche quando i dati risiedono fisicamente nell''Unione Europea. Lo strumento soddisfa pertanto il requisito di residenza del dato, ma non un eventuale requisito contrattuale di trattamento da parte di un responsabile stabilito esclusivamente nell''UE. Qualora un cliente ponga questo vincolo, i componenti di archiviazione ed elaborazione vanno migrati su fornitori europei (per esempio Scaleway, OVHcloud, Hetzner, Exoscale), con un impatto sui costi operativi.\n\nAdempimenti a carico dell''operatore dello strumento: stipula dei DPA con i fornitori, mantenimento aggiornato dell''elenco dei sub-responsabili, verifica delle basi giuridiche per il trattamento.\n\nQuesto testo ha finalità informativa e non costituisce consulenza legale. Prima di utilizzarlo in un contesto contrattuale o di riprodurlo in un''informativa verso i clienti, sottoporlo a un consulente legale."
  }'::jsonb
);

insert into legal_texts (key, content) values (
  'pdf_footer_notice',
  '{
    "en": "Data stored in the EU. See the Data & Privacy page for details.",
    "it": "Dati archiviati nell''UE. Vedi la pagina Dati e privacy per i dettagli."
  }'::jsonb
);
