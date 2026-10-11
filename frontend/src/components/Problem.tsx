import { OFFLINE } from "../labels";
import { href } from "../route";
import Icon from "./Icon";

/** A failure as the page shows it: what happened in a plain sentence, what to do about it when
 *  we know, whether Settings is where to do it, and the original words behind "Details". */
export type Explanation = { text: string; fix?: string; settings?: boolean; details?: string };

/** The Anthropic SDK's own words for missing or wrong auth; a bare 401 counts only when the
 *  message says it came from Anthropic or Claude (other services return 401s too). */
function anthropicAuth(message: string): boolean {
  if (message.includes("Could not resolve authentication method") || /invalid x-api-key/i.test(message)) return true;
  return /\b401\b/.test(message) && /anthropic|claude/i.test(message);
}

type Rule = { when: (m: string) => boolean; say: (m: string) => Explanation };

const first = (m: string) => m.split("\n")[0];

/** Known failures, most specific first. Each one names the fix; the rest fall through to the
 *  message's first line with the full text behind Details. */
const RULES: Rule[] = [
  // Before the Anthropic rule: a key Anthropic refuses also says "invalid x-api-key".
  { when: (m) => m.includes("didn't accept that API key"),
    say: (m) => ({ text: m.replace(/ \(.*\)$/s, ""), fix: "Paste the key again in Settings, or make a new one with your provider.", settings: true, details: m }) },
  { when: anthropicAuth,
    say: (m) => ({ text: "Claude isn't signed in.", fix: "Add your Anthropic API key in Settings.", settings: true, details: m }) },
  { when: (m) => /^No .+ API key yet/.test(m),
    say: (m) => ({ text: m.replace(/ Add one in Settings\.$/, ""), fix: "Add the key in Settings, then press Retry.", settings: true }) },
  { when: (m) => /^No .+ model chosen yet/.test(m),
    say: (m) => ({ text: m.replace(/ Pick one in Settings\.$/, ""), fix: "Choose a model in Settings, then press Retry.", settings: true }) },
  { when: (m) => /\b429\b|rate.?limit|quota|credit balance|billing|overloaded/i.test(m) && !/youtube/i.test(m),
    say: (m) => ({ text: "Your AI provider turned the request away: a rate limit, or no credit left.",
                   fix: "Wait a minute and press Retry. If it keeps happening, check your plan and billing with the provider.", details: m }) },
  { when: (m) => (m.includes("No option name near") && m.includes(".ass")) || m.includes("No such filter: 'ass'") || m.includes("needs libass"),
    say: (m) => ({ text: "This ffmpeg can't draw captions.", fix: "Open Settings: it shows what is missing and downloads a working ffmpeg.", settings: true, details: m }) },
  { when: (m) => /Bad CPU type|No such file or directory: '?(ffmpeg|ffprobe)|(ffmpeg|ffprobe): (command )?not found|doesn't run on this computer/.test(m),
    say: (m) => ({ text: "ffmpeg is missing or can't run on this computer.", fix: "Open Settings: Clipper downloads its own copy and shows the progress there.", settings: true, details: m }) },
  { when: (m) => /(model|font) missing|Missing .*(Montserrat|face_landmarker)/i.test(m),
    say: (m) => ({ text: "A file Clipper needs isn't installed yet.", fix: "Open Settings to see which one and how to get it.", settings: true, details: m }) },
  { when: (m) => /yt-dlp needs updating|unable to extract/i.test(m),
    say: (m) => ({ text: "YouTube changed something and the downloader is out of date.",
                   fix: "Stop Clipper and run ./start again (it updates the downloader), then press Retry. Or download the video yourself and use Choose file… in New.", details: m }) },
  { when: (m) => /YouTube refused|HTTP Error 403|not a bot/i.test(m),
    say: (m) => ({ text: "YouTube refused the download.",
                   fix: "Wait a few minutes and press Retry. If it keeps happening, download the video yourself and use Choose file… in New.", details: m }) },
  { when: (m) => /^This video is (private|unavailable|age-restricted)/.test(m),
    say: (m) => ({ text: first(m), fix: "If you have the video, download it yourself and use Choose file… in New." }) },
  { when: (m) => /No space left on device/i.test(m),
    say: (m) => ({ text: "This computer's disk is full.", fix: "Free some space (old jobs in the jobs folder are safe to delete), then press Retry.", details: m }) },
  { when: (m) => /^[\w-]+\.yaml(:| is not valid YAML)/.test(m) || m.startsWith("Campaign file not found"),
    say: (m) => ({ text: first(m), fix: "Fix that file in the campaigns folder, then try again." }) },
  { when: (m) => m.includes("Failed to fetch") || m.includes("NetworkError") || m.includes("Load failed"),
    say: () => ({ text: OFFLINE, fix: "If this doesn't clear up, start Clipper again (./start) and reload this page." }) },
  { when: (m) => m === "Internal Server Error" || m.startsWith("Clipper hit an unexpected error"),
    say: (m) => ({ text: "Clipper hit an unexpected error.",
                   fix: "Try again. If it keeps happening, the reason is in the terminal running Clipper (or ~/Library/Logs/Clipper.log).",
                   ...(m === "Internal Server Error" ? {} : { details: m }) }) },
];

export function explain(message: string): Explanation {
  if (message.startsWith("Something in Clipper's page broke")) {
    return { text: first(message), fix: "Reload the page. If it happens again in the same place, please report it with the details below.", details: message };
  }
  const rule = RULES.find((r) => r.when(message));
  if (rule) return rule.say(message);
  const [head, ...rest] = message.split("\n");
  return rest.length > 0 ? { text: head, details: message } : { text: head };
}

/** An error where it happened: what went wrong, how to fix it, a way to Settings when that is
 *  where the fix is, an optional dismiss, and the original message behind Details. Its
 *  role="alert" announces it once, on mount — so it doesn't also go through announce(), which
 *  would read it twice. A `persistent` problem (one that stays on screen across polls, like a
 *  failed row) is a quieter role="status" instead. */
export default function Problem({ message, onDismiss, persistent = false, inSettings = false }: {
  message: string; onDismiss?: () => void; persistent?: boolean;
  inSettings?: boolean;             // already on the Settings page: no link to it
}) {
  const { text, fix, settings, details } = explain(message);
  return (
    <div className="problem" role={persistent ? "status" : "alert"}>
      <Icon name="alert" />
      <div className="problem-body">
        <p className="problem-what">{text}</p>
        {fix && <p className="fix"><b>How to fix:</b> {fix}</p>}
        {settings && !inSettings && <a className="button soft" href={href({ id: null, settings: true })}><Icon name="gear" />Open Settings</a>}
        {details && details !== text && (
          <details>
            <summary>Details</summary>
            <pre>{details}</pre>
          </details>
        )}
      </div>
      {onDismiss && (
        <button type="button" className="ghost icon-only" aria-label="Dismiss" onClick={onDismiss}><Icon name="x" /></button>
      )}
    </div>
  );
}
