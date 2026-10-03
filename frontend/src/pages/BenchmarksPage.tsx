import {
  AlertCircle,
  BarChart3,
  Clock3,
  Cpu,
  Database,
  ExternalLink,
  FileText,
  Info,
  Target,
} from 'lucide-react';
import type { JSX } from 'react';
import { BENCHMARK } from '../api/benchmarkData.ts';
import { PageHeader } from '../components/common/Ui.tsx';
import {
  ActivityGrid,
  AdditionalMetricsTiles,
  AlertTimeline,
  ConfusionMatrix,
  FalseAlarmEvidence,
  KpiCard,
  TestDatasetTable,
  VersionComparisonBars,
} from '../features/benchmarks/BenchmarkCharts.tsx';
import { FieldAccuracy } from '../features/benchmarks/FieldAccuracy.tsx';
import './EngineeringPages.css';
import './BenchmarksPage.css';

export function BenchmarksPage(): JSX.Element {
  const b = BENCHMARK;

  return (
    <div className="engineering-page benchmarks-page">
      <PageHeader
        eyebrow="SYSTEM"
        title="How accurate is fall detection?"
        subtitle={`Results from your own rooms first, then the frozen model ${b.model} tested once on the sealed ${b.dataset} recordings.`}
      >
        <span className="bm-eval-warning-pill" role="status">
          <span className="bm-eval-warning-icon" aria-hidden="true"><AlertCircle /></span>
          <span className="bm-eval-warning-text">False-alarm rate under evaluation</span>
        </span>
        <span className="bm-dataset-label">
          <Database className="bm-dataset-cal-icon" aria-hidden="true" />
          <span>{b.dataset} · {b.model}</span>
        </span>
      </PageHeader>

      <section className="bm-card bm-limits-card" aria-labelledby="bm-limits-title">
        <div className="bm-card-header">
          <div className="bm-card-title-group">
            <span className="bm-card-icon bm-icon-blue" aria-hidden="true"><AlertCircle /></span>
            <h2 id="bm-limits-title">Read these limits first</h2>
          </div>
        </div>
        <ul className="bm-limits-list">
          {b.limitations.map((item) => <li key={item}>{item}</li>)}
        </ul>
      </section>

      <FieldAccuracy />

      {/* Row 1: 3 KPI Cards */}
      <section className="bm-kpi-row" aria-label="Headline results on the sealed test">
        <KpiCard
          tone="blue"
          icon={<Target />}
          label="Recall"
          value={`${b.recall}%`}
          description="Correctly detected falls"
          evidence={[`95% CI ${b.recallInterval}`, `Gate ≥ ${b.gates.minRecall}% · passed`]}
          accessibleLabel={`Recall ${b.recall}%, 95% confidence ${b.recallInterval}, gate at least ${b.gates.minRecall}%: passed`}
        />
        <KpiCard
          tone="green"
          icon={<BarChart3 />}
          label="Precision"
          value={`${b.precision}%`}
          description="Correct positive predictions"
          evidence={[`95% CI ${b.precisionInterval}`, `Gate ≥ ${b.gates.minPrecision}% · passed`]}
          accessibleLabel={`Precision ${b.precision}%, 95% confidence ${b.precisionInterval}, gate at least ${b.gates.minPrecision}%: passed`}
        />
        <KpiCard
          tone="violet"
          icon={<Clock3 />}
          label="p95 Time-to-Alert"
          value={`${b.p95Seconds.toFixed(2)} s`}
          description="Time from fall to alert"
          evidence={[`Median ${b.medianSeconds.toFixed(2)} s`, `Gate ≤ ${b.gates.maxP95Seconds} s · passed`]}
          accessibleLabel={`p95 time to alert ${b.p95Seconds} seconds, gate at most 3 seconds: passed`}
        />
      </section>

      {/* Row 2: 3 Cards (Confusion Matrix, PR Curve, Version Comparison) */}
      <section className="bm-middle-grid" aria-label="Model performance charts">
        {/* Card 1: Confusion Matrix */}
        <div className="bm-card">
          <div className="bm-card-header">
            <div className="bm-card-title-group">
              <span className="bm-card-icon bm-icon-blue" aria-hidden="true">
                <Cpu />
              </span>
              <h2>Confusion matrix</h2>
            </div>
          </div>
          <p className="bm-card-caption">Clip counts on the sealed Test-B.</p>
          <div className="bm-card-body">
            <ConfusionMatrix />
          </div>
        </div>

        {/* Card 2: Precision-Recall Curve */}
        <div className="bm-card">
          <div className="bm-card-header">
            <div className="bm-card-title-group">
              <span className="bm-card-icon bm-icon-blue" aria-hidden="true">
                <AlertCircle />
              </span>
              <h2>False-alarm rate</h2>
            </div>
          </div>
          <p className="bm-card-caption">False alarms on held-out everyday recordings, against the target rate.</p>
          <div className="bm-card-body">
            <FalseAlarmEvidence />
          </div>
        </div>

        {/* Card 3: Model Version Comparison */}
        <div className="bm-card">
          <div className="bm-card-header">
            <div className="bm-card-title-group">
              <span className="bm-card-icon bm-icon-blue" aria-hidden="true">
                <FileText />
              </span>
              <h2>Model version comparison</h2>
            </div>
          </div>
          <p className="bm-card-caption">Development diagnostics only: V6.2 was never run on the sealed Test-B.</p>
          <div className="bm-card-body">
            <VersionComparisonBars />
          </div>
        </div>
      </section>

      {/* Row 3: Bottom Row (Additional Metrics + Test Dataset) */}
      <section className="bm-bottom-grid" aria-label="Further metrics and dataset">
        {/* Additional Metrics */}
        <div className="bm-card bm-add-metrics-card">
          <div className="bm-card-header">
            <div className="bm-card-title-group">
              <span className="bm-card-icon bm-icon-blue" aria-hidden="true">
                <FileText />
              </span>
              <h2>Additional metrics</h2>
            </div>
          </div>
          <p className="bm-card-caption">Further results from the sealed Test-B evaluation.</p>
          <div className="bm-card-body">
            <AdditionalMetricsTiles />
          </div>
        </div>

        {/* Test Dataset */}
        <div className="bm-card bm-test-dataset-card">
          <div className="bm-card-header">
            <div className="bm-card-title-group">
              <span className="bm-card-icon bm-icon-blue" aria-hidden="true">
                <Database />
              </span>
              <h2>Test dataset</h2>
            </div>
          </div>
          <div className="bm-card-body">
            <TestDatasetTable />
          </div>
        </div>
      </section>

      {/* Audit Trail & Detailed Breakdown Card */}
      <section className="bm-card bm-audit-card" aria-label="Audit trail and detailed evidence">
        <div className="bm-card-header bm-audit-card-header">
          <div className="bm-card-title-group">
            <span className="bm-card-icon bm-icon-blue" aria-hidden="true">
              <FileText />
            </span>
            <div>
              <h2>Audit trail and detailed breakdown</h2>
              <p className="bm-audit-subtitle">
                Activity-level classification, fall latency distribution, and evaluation provenance
              </p>
            </div>
          </div>
          <div className="bm-audit-header-tags" aria-hidden="true">
            <span className="bm-audit-tag tag-blue">132 Sealed Clips</span>
            <span className="bm-audit-tag tag-teal">59/60 Falls Detected</span>
          </div>
        </div>

        <div className="bm-card-body">
          <div className="bm-audit-grid">
            {/* Left: Activity breakdown */}
            <div className="bm-audit-subcard">
              <div className="bm-subcard-header">
                <h3>Results by activity</h3>
                <span className="bm-subcard-caption">Per-clip classification outcome</span>
              </div>
              <ActivityGrid />
            </div>

            {/* Right: Time to Alert Timeline */}
            <div className="bm-audit-subcard">
              <div className="bm-subcard-header">
                <h3>Time to alert, every detected fall</h3>
                <span className="bm-subcard-caption">Seconds from onset to alert (59 events)</span>
              </div>
              <AlertTimeline />
              <p className="engineering-note">
                <Info aria-hidden="true" />
                Development diagnostics (out-of-fold dev data and Test-X), not the sealed test: only {b.model} was run on Test-B. V6.3 traded a few more dev false alarms for far better camera-2 recall.
              </p>
            </div>
          </div>

          <div className="bm-audit-footer">
            <a
              className="bm-report-link"
              href={b.reportUrl}
              target="_blank"
              rel="noreferrer"
            >
              <ExternalLink aria-hidden="true" />
              <span>Read the full evaluation report ({b.evaluationCommit})</span>
            </a>
            <p className="bm-poc-boundary">
              Research prototype, not a certified medical device or an emergency service.
            </p>
          </div>
        </div>
      </section>
    </div>
  );
}
