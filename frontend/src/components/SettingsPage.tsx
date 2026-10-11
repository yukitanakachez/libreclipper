import { useEffect, useId, useState, type FormEvent } from "react";
import { api } from "../api";
import { notifyChanged } from "../changes";
import { href } from "../route";
import type { ProviderInfo, Settings, SetupCheck } from "../types";
import Icon from "./Icon";
import Problem from "./Problem";
import ProviderLogo from "./ProviderLogo";

/** Where the key in use comes from, when there is one: nothing to say otherwise. */
function keyNote(p: ProviderInfo): string | null {
  if (p.key_source === "saved") return `A key is saved${p.key_hint ? ` (ends in ${p.key_hint})` : ""}. Type a new one to replace it.`;
  if (p.key_source) return `Using ${p.key_source} from your shell.`;
  if (p.needs_key && p.ready) return "Signed in with ant auth login.";
  return null;
}

/** One provider's key and model: shown for the provider picked above, saved with one button. */
function ProviderForm({ provider: p, onSaved }: { provider: ProviderInfo; onSaved: (s: Settings) => void }) {
  const id = useId();
  const [key, setKey] = useState("");
  const [model, setModel] = useState(p.model);
  const [models, setModels] = useState<string[] | null>(null);
  const [checking, setChecking] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const canAsk = !p.needs_key || key.trim() !== "" || p.ready;

  async function check() {
    setChecking(true); setError(null); setNote(null);
    try {
      const { models: list } = await api.listModels(p.id, key.trim() || undefined);
      setModels(list);
      if (!model && list.length > 0 && p.id !== "anthropic") setModel(list[0]);
      setNote(p.needs_key ? `The key works: ${list.length} models to choose from.` : `${list.length} models found.`);
    } catch (e) { setModels(null); setError((e as Error).message); }
    finally { setChecking(false); }
  }

  async function save(e: FormEvent) {
    e.preventDefault();
    setSaving(true); setError(null); setNote(null);
    try {
      onSaved(await api.saveSettings({ provider: p.id, model: model.trim(), ...(key.trim() ? { api_key: key.trim() } : {}) }));
      setKey("");
      setNote(`Saved. Clipper now picks moments with ${p.name}.`);
      notifyChanged();
    } catch (err) { setError((err as Error).message); }
    finally { setSaving(false); }
  }

  // Anthropic has a default model (config.yaml's); everyone else needs one named.
  const needsModel = p.id !== "anthropic";
  const canSave = canAsk && (!needsModel || model.trim() !== "");

  return (
    <form className="provider-form" onSubmit={save} aria-label={`${p.name} settings`}>
      {p.needs_key && (
        <label htmlFor={`${id}-key`}>API key
          <span className="key-row">
            <input id={`${id}-key`} type="password" autoComplete="off" spellCheck={false} value={key}
                   placeholder={p.has_key ? "••••••••••••" : "Paste your key"}
                   onChange={(e) => { setKey(e.target.value); setNote(null); }} />
            {p.key_url && <a className="button soft" href={p.key_url} target="_blank" rel="noreferrer">
              <Icon name="external" />Get a key</a>}
          </span>
          {keyNote(p) && <small className="muted">{keyNote(p)}</small>}
        </label>
      )}
      <label htmlFor={`${id}-model`}>Model
        <span className="key-row">
          {models && models.length > 0 ? (
            <select id={`${id}-model`} value={model} onChange={(e) => setModel(e.target.value)}>
              {!needsModel && <option value="">Default (from config.yaml)</option>}
              {model && !models.includes(model) && <option value={model}>{model}</option>}
              {models.map((m) => <option key={m} value={m}>{m}</option>)}
            </select>
          ) : (
            <input id={`${id}-model`} value={model} spellCheck={false} onChange={(e) => setModel(e.target.value)}
                   placeholder={needsModel ? "Model name" : "Default (from config.yaml)"} />
          )}
          <button type="button" disabled={!canAsk || checking} onClick={check}>
            <Icon name="check" />{checking ? "Checking…" : p.needs_key ? "Check key & list models" : "List models"}</button>
        </span>
      </label>
      {error && <Problem message={error} inSettings onDismiss={() => setError(null)} />}
      <div className="actions">
        <button className="primary" disabled={!canSave || saving}>{saving ? "Saving…" : `Use ${p.name}`}</button>
        {note && <span className="ok" role="status">{note}</span>}
      </div>
    </form>
  );
}

/** The rest of the install, as `clipper doctor` sees it: what's missing and how to fix it. */
function Checks() {
  const [checks, setChecks] = useState<SetupCheck[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [round, setRound] = useState(0);
  useEffect(() => {
    let live = true;
    setChecks(null); setError(null);
    api.setupChecks().then((list) => { if (live) setChecks(list); })
      .catch((e: Error) => { if (live) setError(e.message); });
    return () => { live = false; };
  }, [round]);

  const failing = checks?.filter((c) => !c.ok) ?? [];
  // A missing tool that is being downloaded says so in its fix text: keep its progress fresh.
  const downloading = failing.some((c) => c.fix.startsWith("Downloading"));
  useEffect(() => {
    if (!downloading) return;
    const timer = window.setInterval(() => {
      api.setupChecks().then(setChecks).catch(() => undefined);
    }, 3000);
    return () => window.clearInterval(timer);
  }, [downloading]);
  return (
    <section className="settings-section" aria-labelledby="checks-title">
      <div className="settings-head">
        <h3 id="checks-title">This computer</h3>
        <button type="button" className="ghost" onClick={() => setRound(round + 1)}><Icon name="retry" />Check again</button>
      </div>
      {error && <Problem message={error} inSettings />}
      {!checks && !error && <p className="muted">Checking ffmpeg, fonts and models…</p>}
      {checks && failing.length === 0 && <p className="ok">Everything Clipper needs is installed.</p>}
      {checks && (
        <ul className="checks">
          {checks.map((c) => (
            <li key={c.name} className={c.ok ? "good" : "bad"}>
              <Icon name={c.ok ? "check" : "alert"} />
              <span><b>{c.name}</b>{!c.ok && <small>{c.fix}</small>}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

/**
 * Settings, and the first thing a new install shows (`setup`): choose the one AI provider that
 * picks the moments, give it a key and a model, and see whether the rest of the install is
 * complete. Exactly one provider is in use at a time; the others keep their keys.
 */
export default function SettingsPage({ settings, setup = false, onSaved }: {
  settings: Settings | null; setup?: boolean; onSaved: (s: Settings) => void;
}) {
  const [picked, setPicked] = useState<string | null>(null);
  const [configError, setConfigError] = useState<string | null>(null);
  if (!settings) {
    return <div className="settings-page" tabIndex={-1}><div className="skeleton" style={{ height: 32, width: 240 }} /><div className="skeleton" style={{ height: 160 }} /></div>;
  }
  const shown = settings.providers.find((p) => p.id === (picked ?? settings.using)) ?? settings.providers[0];

  return (
    <div className="settings-page" tabIndex={-1}>
      <h2>{setup ? "Set up Clipper" : "Settings"}</h2>

      <section className="settings-section" aria-labelledby="ai-title">
        <h3 id="ai-title">AI provider</h3>
        <div className="providers" role="radiogroup" aria-labelledby="ai-title">
          {settings.providers.map((p) => {
            const inUse = settings.ready && p.id === settings.using;
            return (
              <label key={p.id} className={`provider ${p.id === shown.id ? "on" : ""}`}>
                <input type="radio" name="provider" className="visually-hidden" value={p.id}
                       checked={p.id === shown.id} onChange={() => setPicked(p.id)} />
                <ProviderLogo id={p.id} name={p.name} />
                <span className="provider-name">{p.name}</span>
                <span className={`provider-state ${inUse ? "ok" : "muted"}`}>
                  {inUse ? "In use" : p.ready ? (p.needs_key ? "Key saved" : "No key needed") : "No key yet"}
                </span>
              </label>
            );
          })}
        </div>
        <ProviderForm key={shown.id} provider={shown} onSaved={onSaved} />
      </section>

      <Checks />

      <div className="actions">
        {setup && settings.ready && <a className="button primary" href={href({ id: null })}>Done</a>}
        <button type="button" className="ghost" onClick={async () => {
          setConfigError(null);
          try { await api.revealConfig(); } catch (e) { setConfigError((e as Error).message); }
        }}><Icon name="folder" />Show config.yaml</button>
      </div>
      {configError && <Problem message={configError} inSettings onDismiss={() => setConfigError(null)} />}
    </div>
  );
}
