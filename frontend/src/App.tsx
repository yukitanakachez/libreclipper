import { useEffect, useState, type MouseEvent } from "react";
import { api } from "./api";
import Announcer from "./components/Announcer";
import ClipWorkspace from "./components/ClipWorkspace";
import Dialog from "./components/Dialog";
import JobList from "./components/JobList";
import NewSheet from "./components/NewSheet";
import NextUp from "./components/NextUp";
import { OrbGrain } from "./components/Orb";
import RenderedPage from "./components/RenderedPage";
import SettingsPage from "./components/SettingsPage";
import ShortcutList from "./components/ShortcutList";
import { Backdrop } from "./components/Texture";
import TopBar from "./components/TopBar";
import { buildNotifications } from "./inbox";
import { unposted } from "./listItems";
import { useRoute } from "./route";
import type { Settings } from "./types";
import "./styles.css";
import { useJobList } from "./useJobList";
import useShortcuts from "./useShortcuts";

const MAIN = "main";

/** Moves focus to the workspace (past the list column), else the page area, without touching
 *  the hash (the hash is the route). Both carry tabIndex={-1} so they can take focus. */
function skipToMain(e: MouseEvent) {
  e.preventDefault();
  const main = document.getElementById(MAIN);
  (main?.querySelector<HTMLElement>(".workspace, .next-up, .rendered-page, .settings-page") ?? main)?.focus();
}

export default function App() {
  const route = useRoute();
  const jobs = useJobList();
  // Which AI provider is in use. Until one is ready, the board gives way to the setup page.
  const [settings, setSettings] = useState<Settings | null>(null);
  useEffect(() => { api.getSettings().then(setSettings).catch(() => undefined); }, []);
  const setup = settings !== null && !settings.ready && !route.id && !route.rendered;
  const onSettings = !!route.settings || setup;
  const [newOpen, setNewOpen] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  const onNew = () => setNewOpen(true);

  useShortcuts({
    n: onNew,
    "?": () => setHelpOpen(true),
  });

  // The window title and the top bar's breadcrumb: the open job or page, else the board.
  const open = onSettings ? (setup ? "Set up" : "Settings") : route.rendered ? "Rendered clips"
    : route.id ? jobs.items.find((i) => i.id === route.id)?.title : undefined;
  useEffect(() => { document.title = open ? `${open} · Clipper` : "Clipper"; }, [open]);

  return (
    <>
      <a className="skip-link" href={`#${MAIN}`} onClick={skipToMain}>Skip to workspace</a>
      <Announcer />
      <OrbGrain />
      <Backdrop />
      <div className="shell">
        <TopBar title={open} notes={buildNotifications(jobs.items)} toPost={unposted(jobs.items)}
                onRendered={!!route.rendered} onSettings={onSettings} onNew={onNew} onHelp={() => setHelpOpen(true)} />
        <main id={MAIN} tabIndex={-1} className={route.id ? "main" : "main home"}>
          {onSettings ? <SettingsPage settings={settings} setup={setup} onSaved={setSettings} />
            : route.rendered ? <RenderedPage /> : route.id ? (
            // An open clip job fills both cells: its moments in the list column, then the workspace.
            <ClipWorkspace key={route.id} jobId={route.id} />
          ) : (
            // Nothing open: Next up across the top, then every job as a board of cards.
            <>
              <NextUp jobs={jobs} onNew={onNew} />
              <JobList jobs={jobs} />
            </>
          )}
        </main>
      </div>
      {newOpen && <NewSheet onClose={() => setNewOpen(false)} />}
      {helpOpen && (
        <Dialog title="Keyboard shortcuts" onClose={() => setHelpOpen(false)}>
          <ShortcutList />
        </Dialog>
      )}
    </>
  );
}
