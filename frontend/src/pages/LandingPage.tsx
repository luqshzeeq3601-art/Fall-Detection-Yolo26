import { Activity, ArrowRight, ArrowRightLeft, BarChart3, Camera, ClipboardCheck, Cpu, Database, Film, Heart, IdCard, Image as ImageIcon, Lock, Server, Share2, ShieldCheck, Users } from 'lucide-react';
import type { JSX } from 'react';
import { Link } from 'react-router-dom';
import { BENCHMARK } from '../api/benchmarkData.ts';
import { Brand } from '../components/layout/Brand.tsx';
import heroArtUrl from '../assets/hero-reference-v2.png';
import workflowCameraUrl from '../assets/workflow-camera.png';
import workflowMovementUrl from '../assets/workflow-movement.png';
import workflowReviewUrl from '../assets/workflow-review.png';
import { useAuth } from '../features/auth/useAuth.ts';
import './LandingPage.css';

// 3-step evidence workflow matching heropc.png and 01-landing.md
const WORKFLOW_STEPS = [
  {
    step: '1',
    icon: <Camera />,
    iconColor: 'blue',
    art: workflowCameraUrl,
    artWidth: 1536,
    artHeight: 1024,
    title: 'Capture a private evidence clip',
    body: 'When a possible fall is detected, the device stores a short local sequence for review.',
  },
  {
    step: '2',
    icon: <ImageIcon />,
    iconColor: 'mint',
    art: workflowMovementUrl,
    artWidth: 1448,
    artHeight: 1086,
    title: 'Review movement over time',
    body: 'Compare before, during, and after frames to understand context and reduce false alerts.',
  },
  {
    step: '3',
    icon: <Users />,
    iconColor: 'violet',
    art: workflowReviewUrl,
    artWidth: 1536,
    artHeight: 1024,
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
    body: 'Evaluated in controlled study conditions. This describes study context, not a medical guarantee.',
    tags: [
      { icon: <IdCard />, label: 'STUDY ID', value: 'ECV-RESEARCH-001' },
      { icon: <Database />, label: 'DATASET', value: 'De-identified internal set' },
    ],
  },
  {
    icon: <Cpu />,
    title: 'Temporal evidence processed locally',
    badge: 'Local inference',
    badgeColor: 'mint',
    body: 'Detection runs locally first and creates short evidence clips for incident review.',
    tags: [
      { icon: <Film />, label: 'SEQUENCE FORMAT', value: 'Short MP4 clip' },
      { icon: <Server />, label: 'STORAGE', value: 'Configured local server' },
    ],
  },
  {
    icon: <Lock />,
    title: 'Privacy and evidence handling',
    badge: 'Configurable sharing',
    badgeColor: 'violet',
    body: 'Inference is local. Optional VLM enrichment may share evidence images. Uploaded videos remain on the configured server.',
    tags: [
      { icon: <ArrowRightLeft />, label: 'DATA FLOW', value: 'Local inference first' },
      { icon: <Share2 />, label: 'SHARING', value: 'Configurable evidence images' },
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
              RESEARCH PROTOTYPE
            </p>
            <h1 id="landing-title">
              See evidence<br />
              <span>between camera<br />and caregiver.</span>
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

          <div className="landing-hero-art">
            <img
              className="landing-hero-illustration"
              src={heroArtUrl}
              alt="Synthetic illustration of a camera, caregiver phone, and three evidence frames showing movement over time."
            />
          </div>
        </section>

        <div className="landing-proof">
        {/* WORKFLOW SECTION (#how-it-works) */}
        <section className="landing-section landing-workflow" id="how-it-works" aria-labelledby="how-title">
          <header className="landing-section-head">
            <p className="landing-kicker">How it works</p>
            <h2 id="how-title">From camera to caregiver<br />in <span>three steps</span></h2>
          </header>
          <ol className="landing-steps">
            {WORKFLOW_STEPS.map((step, index) => (
              <li key={step.title} className={`landing-step landing-step-${step.iconColor}`}>
                <div className="landing-step-top">
                  <span className="landing-step-index" aria-hidden="true">
                    {step.step}
                  </span>
                  <span className={`landing-feature-icon landing-feature-icon-${step.iconColor}`} aria-hidden="true">
                    {step.icon}
                  </span>
                </div>
                <img className="landing-step-art" src={step.art} alt="" loading="lazy" width={step.artWidth} height={step.artHeight} />
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
        <section className="landing-section landing-results" id="results" aria-labelledby="results-title">
          <header className="landing-section-head">
            <p className="landing-kicker">Results</p>
            <h2 id="results-title">Tested on <span>{BENCHMARK.clips} recordings</span><br />it had never seen</h2>
            <p>
              {BENCHMARK.fallClips} falls and {BENCHMARK.adlClips} everyday activities (sitting,
              bending, lying down) from the sealed {BENCHMARK.dataset} set.
            </p>
            <p className="landing-note">
              False alarms per hour in real homes are under evaluation (0.83 h held-out exposure; target unproven).{' '}
              <a href={BENCHMARK.reportUrl} target="_blank" rel="noreferrer">
                Read the full evaluation report.
              </a>
            </p>
          </header>
          <div className="landing-metrics" aria-label="Measured evaluation results">
            <div className="landing-metric landing-metric-blue">
              <span className="landing-metric-icon" aria-hidden="true">
                <BarChart3 />
              </span>
              <span>
                <strong>{BENCHMARK.recall.toFixed(1)}%</strong>
                <span>of falls detected (59 of 60)</span>
              </span>
              <div className="landing-metric-wave" aria-hidden="true" />
            </div>
            <div className="landing-metric landing-metric-mint">
              <span className="landing-metric-icon" aria-hidden="true">
                <ClipboardCheck />
              </span>
              <span>
                <strong>{BENCHMARK.precision.toFixed(1)}%</strong>
                <span>of alerts were real falls</span>
              </span>
              <div className="landing-metric-wave" aria-hidden="true" />
            </div>
            <div className="landing-metric landing-metric-violet">
              <span className="landing-metric-icon" aria-hidden="true">
                <Activity />
              </span>
              <span>
                <strong>{BENCHMARK.p95Seconds.toFixed(2)} s</strong>
                <span>from fall to alert (95% of cases)</span>
              </span>
              <div className="landing-metric-wave" aria-hidden="true" />
            </div>
          </div>
        </section>
        </div>

        <div className="landing-closing">
        {/* PRIVACY & HANDLING SECTION (#privacy) */}
        <section className="landing-section landing-privacy" id="privacy" aria-labelledby="privacy-title">
          <header className="landing-section-head">
            <p className="landing-kicker">Privacy & Evidence</p>
            <h2 id="privacy-title">Designed to protect privacy while preserving proof</h2>
          </header>
          <div className="landing-feature-grid landing-bento-grid">
            {PRIVACY_CARDS.map((item) => (
              <article className={`landing-feature-card landing-privacy-card-${item.badgeColor}`} key={item.title}>
                <div className="landing-card-topbar">
                  <span className="landing-feature-icon" aria-hidden="true">
                    {item.icon}
                  </span>
                  <span className={`landing-badge landing-badge-${item.badgeColor}`}>
                    {item.badge}
                  </span>
                </div>
                <h3>{item.title}</h3>
                <p>{item.body}</p>
                <dl className="landing-tag-row">
                  {item.tags.map((t) => (
                    <div className="landing-tag" key={t.label}>
                      <span className="landing-tag-icon" aria-hidden="true">{t.icon}</span>
                      <div className="landing-tag-copy">
                        <dt className="landing-tag-label">{t.label}</dt>
                        <dd className="landing-tag-val">{t.value}</dd>
                      </div>
                    </div>
                  ))}
                </dl>
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
        </div>
      </main>

      <footer className="landing-footnote">
        <p>ElderCare Vision · research prototype, not a certified medical device or emergency service.</p>
      </footer>
    </div>
  );
}
