import type { JSX } from 'react';

export function LoadingState({ label }: { label: string }): JSX.Element {
  return (
    <div role="status" aria-live="polite" className="state state-loading">
      <span aria-hidden="true" className="spinner" />
      <p>{label}</p>
    </div>
  );
}

export function ErrorState({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}): JSX.Element {
  return (
    <div role="alert" className="state state-error">
      <p className="state-title">Something went wrong</p>
      <p>{message}</p>
      {onRetry ? (
        <button type="button" onClick={onRetry}>
          Retry
        </button>
      ) : null}
    </div>
  );
}

export function EmptyState({
  title,
  detail,
}: {
  title: string;
  detail?: string;
}): JSX.Element {
  return (
    <div role="status" className="state state-empty">
      <p className="state-title">{title}</p>
      {detail ? <p>{detail}</p> : null}
    </div>
  );
}
