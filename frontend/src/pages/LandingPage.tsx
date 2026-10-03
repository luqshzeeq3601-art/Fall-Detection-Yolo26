import { Activity, ArrowRight, BarChart3, Camera, ChevronRight, ClipboardCheck, Cpu, Heart, Image as ImageIcon, Lock, ShieldCheck, Users } from 'lucide-react';
import type { JSX } from 'react';
import { Link } from 'react-router-dom';
import { BENCHMARK } from '../api/benchmarkData.ts';
import { Brand } from '../components/layout/Brand.tsx';
import heroArtUrl from '../assets/hero-art.png';
import { useAuth } from '../features/auth/useAuth.ts';
import './LandingPage.css';

// 3-step evidence workflow matching heropc.png and 01-landing.md
const WORKFLOW_STEPS = [
  {
    step: '1',
    icon: <Camera />,
    iconColor: 'blue',
    title: 'Capture a private evidence clip',
    body: 'When a possible fall is detected, the device stores a short local sequence for review.',
  },
  {
    step: '2',
    icon: <ImageIcon />,
    iconColor: 'mint',
    title: 'Review movement over time',
    body: 'Compare before, during, and after frames to understand context and reduce false alerts.',
  },
  {
    step: '3',
    icon: <Users />,
    iconColor: 'violet',
    title: 'Share a qualified incident review',
    body: 'Configured caregivers can receive annotated evidence and concise review notes.',
  },
];

// Evidence & privacy bento cards matching heropc.png
const PRIVACY_CARDS = [
  {
    icon: <BarChart3 />,
    title: 'Measured in controlled evaluation',
    badge: 'Research setting',
    badgeColor: 'amber',
    body: 'This prototype is evaluated in controlled study conditions. The information below describes study context, not a medical guarantee.',
    tags: [
      { label: 'STUDY ID', value: 'ECV-RESEARCH-001' },
      { label: 'DATASET', value: 'De-identified internal set' },
    ],
  },
  {
    icon: <Cpu />,
    title: 'Temporal evidence processed locally',
    badge: 'Local inference',
    badgeColor: 'mint',
    body: 'The core detection pipeline runs locally first, producing short temporal evidence clips for incident review.',
    tags: [
      { label: 'SEQUENCE FORMAT', value: 'Short MP4 clip' },
      { label: 'STORAGE', value: 'Configured local server' },
    ],
  },
  {
    icon: <Lock />,
    title: 'Privacy and evidence handling',
    badge: 'Configurable sharing',
    badgeColor: 'violet',
    body: 'Inference is local while configured VLM enrichment may share incident evidence images. Uploaded videos remain on the configured server.',
    tags: [
      { label: 'DATA FLOW', value: 'Local inference first' },
      { label: 'SHARING', value: 'Configurable evidence images' },
    ],
  },
];

export function LandingPage(): JSX.Element {
  const { status } = useAuth();
  const signedIn = status === 'signed-in';

  return (
    <div className="landing-page">
      <header className="landing-header">
        <Link className="landing-brand" to="/" aria-label="ElderCare Vision home">
          <Brand />
        </Link>
        <nav className="landing-nav" aria-label="On this page">
          <a href="#how-it-works">How it works</a>
          <a href="#results">Results</a>
          <a href="#privacy">Privacy</a>
        </nav>
        <div className="landing-header-actions">
          {signedIn ? (
            <Link className="landing-header-cta" to="/app">
              Open dashboard <ArrowRight aria-hidden="true" />
            </Link>
          ) : (
            <>
              <Link className="landing-signin" to="/signin">
                Sign in
              </Link>
              <Link className="landing-header-cta" to="/signup">
                Create account <ArrowRight aria-hidden="true" />
              </Link>
            </>
          )}
        </div>
      </header>

      <main className="landing-content">
        {/* HERO SECTION */}
        <section className="landing-hero" aria-labelledby="landing-title">
          <div className="landing-hero-copy">
            <p className="landing-eyebrow">
              <span className="landing-eyebrow-dot" aria-hidden="true" /> RESEARCH PROTOTYPE
            </p>
            <h1 id="landing-title">
              See evidence<br />
              <span>between camera and caregiver.</span>
            </h1>
            <p className="landing-hero-subtitle">
              A research prototype for local temporal fall-detection evidence. Review what changed
              across a short sequence, support incident review, and keep inference close to the
              point of care.
            </p>
            <div className="landing-actions">
              <Link
                className="landing-button landing-button-primary"
                to={signedIn ? '/app' : '/signup'}
              >
                {signedIn ? 'Open dashboard' : 'Create account'} <ArrowRight aria-hidden="true" />
              </Link>
              <a className="landing-button landing-button-secondary" href="#how-it-works">
                <BarChart3 aria-hidden="true" /> View workflow
              </a>
              <a className="landing-button landing-button-ghost" href="#results">
                See the results
              </a>
            </div>
            <ul className="landing-trust-list" aria-label="Product principles">
              <li>
                <ShieldCheck aria-hidden="true" /> On-device AI
              </li>
              <li>
                <Heart aria-hidden="true" /> Built for care teams
              </li>
              <li>
                <Activity aria-hidden="true" /> {BENCHMARK.p95Seconds.toFixed(2)} s to alert (p95)
              </li>
            </ul>
          </div>

          <div className="landing-hero-art" aria-hidden="true">
            {/* Synthetic evidence strip preview matching heropc.png */}
            <div className="landing-evidence-preview">
              <div className="landing-evidence-header">
                <ImageIcon className="landing-evidence-icon" aria-hidden="true" />
                <span>Synthetic evidence only</span>
              </div>
              <div className="landing-evidence-frames">
                <div className="landing-frame-item">
                  <div className="landing-frame-thumb landing-frame-t0">
                    <div className="landing-skeleton-stick skeleton-walking" />
                  </div>
                  <span className="landing-frame-stamp">t = 00.0s</span>
                </div>
                <ChevronRight className="landing-frame-arrow" aria-hidden="true" />
                <div className="landing-frame-item">
                  <div className="landing-frame-thumb landing-frame-t1">
                    <div className="landing-skeleton-stick skeleton-falling" />
                  </div>
                  <span className="landing-frame-stamp">t = 01.2s</span>
                </div>
                <ChevronRight className="landing-frame-arrow" aria-hidden="true" />
                <div className="landing-frame-item">
                  <div className="landing-frame-thumb landing-frame-t2">
                    <div className="landing-skeleton-stick skeleton-floor" />
                  </div>
                  <span className="landing-frame-stamp">t = 02.4s</span>
                </div>
              </div>
            </div>
            {/* Background 3D glass camera illustration */}
            <img className="landing-hero-illustration" src={heroArtUrl} alt="" />
          </div>
        </section>

        {/* WORKFLOW SECTION (#how-it-works) */}
        <section className="landing-section" id="how-it-works" aria-labelledby="how-title">
          <header className="landing-section-head">
            <p className="landing-kicker">How it works</p>
            <h2 id="how-title">From camera to caregiver in three steps</h2>
          </header>
          <ol className="landing-steps">
            {WORKFLOW_STEPS.map((step, index) => (
              <li key={step.title} className="landing-step">
                <div className="landing-step-top">
                  <span className="landing-step-index" aria-hidden="true">
                    {step.step}
                  </span>
                  <span className={`landing-feature-icon landing-feature-icon-${step.iconColor}`} aria-hidden="true">
                    {step.icon}
                  </span>
                </div>
                <h3>{step.title}</h3>
                <p>{step.body}</p>
                {index < WORKFLOW_STEPS.length - 1 && (
                  <ArrowRight className="landing-step-connector" aria-hidden="true" />
                )}
              </li>
            ))}
          </ol>
        </section>

        {/* RESULTS SECTION (#results) */}
        <section className="landing-section" id="results" aria-labelledby="results-title">
          <header className="landing-section-head">
            <p className="landing-kicker">Results</p>
            <h2 id="results-title">Tested on {BENCHMARK.clips} recordings it had never seen</h2>
            <p>
              {BENCHMARK.fallClips} falls and {BENCHMARK.adlClips} everyday activities (sitting,
              bending, lying down) from the sealed {BENCHMARK.dataset} set.
            </p>
          </header>
          <div className="landing-metrics" aria-label="Measured evaluation results">
            <div className="landing-metric">
              <span className="landing-metric-icon" aria-hidden="true">
                <BarChart3 />
              </span>
              <span>
                <strong>{BENCHMARK.recall.toFixed(1)}%</strong>
                <span>of falls detected (59 of 60)</span>
              </span>
            </div>
            <div className="landing-metric">
              <span className="landing-metric-icon" aria-hidden="true">
                <ClipboardCheck />
              </span>
              <span>
                <strong>{BENCHMARK.precision.toFixed(1)}%</strong>
                <span>of alerts were real falls</span>
              </span>
            </div>
            <div className="landing-metric">
              <span className="landing-metric-icon" aria-hidden="true">
                <Activity />
              </span>
              <span>
                <strong>{BENCHMARK.p95Seconds.toFixed(2)} s</strong>
                <span>from fall to alert (95% of cases)</span>
              </span>
            </div>
          </div>
          <p className="landing-note">
            False alarms per hour in real homes are under evaluation (0.83 h held-out exposure; target unproven).{' '}
            <a href={BENCHMARK.reportUrl} target="_blank" rel="noreferrer">
              Read the full evaluation report
            </a>
            .
          </p>
        </section>

        {/* PRIVACY & HANDLING SECTION (#privacy) */}
        <section className="landing-section" id="privacy" aria-labelledby="privacy-title">
          <header className="landing-section-head">
            <p className="landing-kicker">Privacy & Evidence</p>
            <h2 id="privacy-title">Designed to protect privacy while preserving proof</h2>
          </header>
          <div className="landing-feature-grid landing-bento-grid">
            {PRIVACY_CARDS.map((item) => (
              <article className="landing-feature-card" key={item.title}>
                <div className="landing-card-topbar">
                  <span className="landing-feature-icon" aria-hidden="true">
                    {item.icon}
                  </span>
                  <span className={`landing-badge landing-badge-${item.badgeColor}`}>
                    <span className="landing-badge-dot" /> {item.badge}
                  </span>
                </div>
                <h3>{item.title}</h3>
                <p>{item.body}</p>
                <div className="landing-tag-row">
                  {item.tags.map((t) => (
                    <div className="landing-tag" key={t.label}>
                      <span className="landing-tag-label">{t.label}</span>
                      <span className="landing-tag-val">{t.value}</span>
                    </div>
                  ))}
                </div>
              </article>
            ))}
          </div>
        </section>

        {/* CTA */}
        <section className="landing-cta" aria-label="Get started">
          <h2>Try it with your own camera or videos</h2>
          <p>Create an account, open Live monitor and press Start.</p>
          <Link
            className="landing-button landing-button-primary"
            to={signedIn ? '/app/surveillance' : '/signup'}
          >
            {signedIn ? 'Open Live monitor' : 'Get started'} <ArrowRight aria-hidden="true" />
          </Link>
        </section>
      </main>

      <footer className="landing-footnote">
        <p>ElderCare Vision · research prototype, not a certified medical device or emergency service.</p>
      </footer>
    </div>
  );
}
