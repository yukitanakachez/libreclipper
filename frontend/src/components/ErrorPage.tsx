import { Component, type ErrorInfo, type ReactNode } from "react";
import { href } from "../route";
import Icon from "./Icon";
import { explain } from "./Problem";

/** A whole page (or workspace) that couldn't be shown: what happened, how to fix it, and the
 *  ways out. `message` is explained the same way as any other error (see Problem). */
export default function ErrorPage({ title, message, onRetry }: {
  title: string; message: string; onRetry?: () => void;
}) {
  const { text, fix, settings, details } = explain(message);
  return (
    <div className="error-page" role="alert">
      <span className="error-mark" aria-hidden="true"><Icon name="alert" /></span>
      <h2>{title}</h2>
      <p>{text}</p>
      {fix && <p className="fix"><b>How to fix:</b> {fix}</p>}
      <div className="actions">
        {onRetry && <button type="button" className="primary" onClick={onRetry}><Icon name="retry" />Try again</button>}
        {settings && <a className="button" href={href({ id: null, settings: true })}><Icon name="gear" />Open Settings</a>}
        <a className="button" href={href({ id: null })}><Icon name="back" />All clip jobs</a>
      </div>
      {details && details !== text && (
        <details>
          <summary>Details</summary>
          <pre>{details}</pre>
        </details>
      )}
    </div>
  );
}

/** Catches a crash while drawing the page, so a bug shows as an error page with a way out
 *  instead of a blank window. */
export class ErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error(error, info.componentStack);
  }

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;
    return (
      <ErrorPage title="This page ran into a problem"
                 message={`Something in Clipper's page broke while it was being drawn.\n${error.stack ?? error.message}`}
                 onRetry={() => window.location.reload()} />
    );
  }
}
