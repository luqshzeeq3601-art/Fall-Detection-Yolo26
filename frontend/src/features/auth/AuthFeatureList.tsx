import { FileText, PersonStanding, ShieldCheck } from 'lucide-react';
import type { JSX } from 'react';

const FEATURES = [
  {
    title: 'Real-time fall detection',
    description: 'Detect potential falls from movement over time.',
    icon: PersonStanding,
    tone: 'blue',
  },
  {
    title: 'Agent-assisted incident insights',
    description: 'Get clear incident summaries with optional AI analysis.',
    icon: FileText,
    tone: 'violet',
  },
  {
    title: 'Privacy-first, on-device AI',
    description: 'Local video analysis with incident evidence for review.',
    icon: ShieldCheck,
    tone: 'mint',
  },
] as const;

export function AuthFeatureList(): JSX.Element {
  return (
    <div className="auth-feature-list">
      {FEATURES.map(({ title, description, icon: Icon, tone }) => (
        <article className="auth-feature-row" key={title}>
          <span className={`auth-feature-icon auth-feature-icon-${tone}`} aria-hidden="true">
            <Icon />
          </span>
          <span className="auth-feature-copy">
            <strong>{title}</strong>
            <small>{description}</small>
          </span>
        </article>
      ))}
    </div>
  );
}
