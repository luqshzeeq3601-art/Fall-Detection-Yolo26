import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  Info,
  Sparkles,
} from 'lucide-react';
import type { JSX, ReactNode } from 'react';
import './Ui.css';
import './Controls.css';

export type Tone = 'blue' | 'green' | 'red' | 'amber' | 'violet' | 'neutral';

export function PageHeader({
  title,
  subtitle,
  eyebrow,
  children,
}: {
  title: string;
  subtitle?: string;
  eyebrow?: string;
  children?: ReactNode;
}): JSX.Element {
  return (
    <header className="page-header">
      <div>
        {eyebrow ? <p className="page-eyebrow">{eyebrow}</p> : null}
        <h1>{title}</h1>
        {subtitle ? <p>{subtitle}</p> : null}
      </div>
      {children ? <div className="page-header-actions">{children}</div> : null}
    </header>
  );
}

export function Card({
  title,
  icon,
  action,
  children,
  className = '',
}: {
  title?: string;
  icon?: ReactNode;
  action?: ReactNode;
  children?: ReactNode;
  className?: string;
}): JSX.Element {
  return (
    <section className={`ui-card ${className}`.trim()}>
      {title || icon || action ? (
        <div className="ui-card-header">
          <div className="ui-card-title">
            {icon ? <span className="ui-card-icon" aria-hidden="true">{icon}</span> : null}
            {title ? <h2>{title}</h2> : null}
          </div>
          {action ? <div className="ui-card-action">{action}</div> : null}
        </div>
      ) : null}
      <div className="ui-card-body">{children}</div>
    </section>
  );
}

export function StatusPill({
  children,
  tone = 'neutral',
  icon,
}: {
  children: ReactNode;
  tone?: Tone;
  icon?: ReactNode;
}): JSX.Element {
  const renderIcon = (): ReactNode => {
    if (icon) return icon;
    switch (tone) {
      case 'amber':
        return <Clock className="status-pill-icon" size={14} strokeWidth={2.4} aria-hidden="true" />;
      case 'green':
        return <CheckCircle2 className="status-pill-icon" size={14} strokeWidth={2.4} aria-hidden="true" />;
      case 'red':
        return <AlertTriangle className="status-pill-icon" size={14} strokeWidth={2.4} aria-hidden="true" />;
      case 'blue':
        return <Info className="status-pill-icon" size={14} strokeWidth={2.4} aria-hidden="true" />;
      case 'violet':
        return <Sparkles className="status-pill-icon" size={14} strokeWidth={2.4} aria-hidden="true" />;
      case 'neutral':
      default:
        return <Clock className="status-pill-icon" size={14} strokeWidth={2.4} aria-hidden="true" />;
    }
  };

  return (
    <span className={`status-pill status-pill-${tone}`}>
      {renderIcon()}
      <span>{children}</span>
    </span>
  );
}

export function MetricCard({
  label,
  value,
  detail,
  tone = 'blue',
  icon,
  children,
}: {
  label: string;
  value: ReactNode;
  detail?: ReactNode;
  tone?: Tone;
  icon?: ReactNode;
  children?: ReactNode;
}): JSX.Element {
  return (
    <article className={`metric-card metric-card-${tone}`}>
      <div className="metric-card-topline">
        <span className="metric-card-label">{label}</span>
        {icon ? <span className="metric-card-icon" aria-hidden="true">{icon}</span> : null}
      </div>
      <div className="metric-card-value-row">
        <strong>{value}</strong>
        {children ? <span className="metric-card-chart" aria-hidden="true">{children}</span> : null}
      </div>
      {detail ? <p className="metric-card-detail">{detail}</p> : null}
    </article>
  );
}
