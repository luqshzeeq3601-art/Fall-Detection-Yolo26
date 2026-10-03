import { Activity, BrainCircuit, ShieldCheck } from 'lucide-react';
import type { JSX } from 'react';

const FEATURES = [
  {
    title: 'Real-time fall detection',
    description: 'Detect potential falls and unusual activity instantly.',
    icon: Activity,
    tone: 'blue',
  },
  {
    title: 'Agent-assisted incident insights',
    description: 'Get clear summaries and recommended actions with AI agents.',
    icon: BrainCircuit,
    tone: 'violet',
  },
  {
    title: 'Privacy-first, on-device AI',
    description: 'Your video stays on-device. Only insights reach your care team.',
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
