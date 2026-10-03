import {
  AlertCircle,
  BarChart3,
  Calendar,
  ChevronDown,
  Clock3,
  Cpu,
  Database,
  ExternalLink,
  FileText,
  Info,
  LineChart,
  Target,
} from 'lucide-react';
import type { JSX } from 'react';
import { BENCHMARK } from '../api/benchmarkData.ts';
import {
  ActivityGrid,
  AdditionalMetricsTiles,
  AlertTimeline,
  ConfusionMatrix,
  KpiCard,
  PrecisionRecallCurve,
  TestDatasetTable,
  VersionComparisonBars,
} from '../features/benchmarks/BenchmarkCharts.tsx';
import './EngineeringPages.css';
import './BenchmarksPage.css';

export function BenchmarksPage(): JSX.Element {
  const b = BENCHMARK;

  return (
    <div className="engineering-page benchmarks-page">
      {/* Top Header Section matching image reference */}
      <header className="bm-page-header">
        <div className="bm-header-titles">
          <span className="bm-header-eyebrow">BENCHMARKS</span>
          <h1 className="bm-header-title" aria-label="Model performance & evaluation">
            Model Performance &amp; Evaluation
          </h1>
          <p className="bm-header-subtitle">
            Frozen model {b.model}, sealed {b.dataset}
          </p>
        </div>

        <div className="bm-header-actions">
          {/* Warning banner pill */}
          <div className="bm-eval-warning-pill" role="status">
            <span className="bm-eval-warning-icon" aria-hidden="true">
              <AlertCircle />
            </span>
            <span className="bm-eval-warning-text">False-alarm rate under evaluation</span>
            <span aria-hidden="true">.</span>
          </div>

          {/* Dataset Selector Dropdown */}
          <div className="bm-dataset-select-btn" role="button" tabIndex={0} aria-label="Select dataset split">
            <Calendar className="bm-dataset-cal-icon" aria-hidden="true" />
            <span className="bm-dataset-select-label">{b.dataset} ({b.model})</span>
            <ChevronDown className="bm-dataset-chevron" aria-hidden="true" />
          </div>
        </div>
      </header>

      {/* Row 1: 3 KPI Cards */}
      <section className="bm-kpi-row" aria-label="Headline results on the sealed test">
        <KpiCard
          tone="blue"
          icon={<Target />}
          label="Recall"
          value={`${b.recall}%`}
          description="Correctly detected falls"
          trend="+0.8%"
          trendDir="up"
          comparisonLabel="vs V6.2"
          accessibleLabel={`Recall ${b.recall}%, 95% confidence ${b.recallInterval}, gate at least ${b.gates.minRecall}%: passed`}
        />
        <KpiCard
          tone="green"
          icon={<BarChart3 />}
          label="Precision"
          value={`${b.precision}%`}
          description="Correct positive predictions"
          trend="+1.1%"
          trendDir="up"
          comparisonLabel="vs V6.2"
          accessibleLabel={`Precision ${b.precision}%, 95% confidence ${b.precisionInterval}, gate at least ${b.gates.minPrecision}%: passed`}
        />
        <KpiCard
          tone="violet"
          icon={<Clock3 />}
          label="p95 Time-to-Alert"
          value={`${b.p95Seconds.toFixed(2)} s`}
          description="Time from fall to alert"
          trend="-0.32 s"
          trendDir="down"
          comparisonLabel="vs V6.2"
          accessibleLabel={`p95 time to alert ${b.p95Seconds} seconds, gate at most 3 seconds: passed`}
        />
      </section>

      {/* Row 2: 3 Cards (Confusion Matrix, PR Curve, Version Comparison) */}
      <section className="bm-middle-grid" aria-label="Model Performance Charts">
        {/* Card 1: Confusion Matrix */}
        <div className="bm-card">
          <div className="bm-card-header">
            <div className="bm-card-title-group">
              <span className="bm-card-icon bm-icon-blue" aria-hidden="true">
                <Cpu />
              </span>
              <h2>Confusion Matrix</h2>
            </div>
            <span className="bm-info-icon" title="Confusion matrix counts on sealed Test-B" aria-label="Confusion matrix info">
              <Info aria-hidden="true" />
            </span>
          </div>
          <div className="bm-card-body">
            <ConfusionMatrix />
          </div>
        </div>

        {/* Card 2: Precision-Recall Curve */}
        <div className="bm-card">
          <div className="bm-card-header">
            <div className="bm-card-title-group">
              <span className="bm-card-icon bm-icon-blue" aria-hidden="true">
                <LineChart />
              </span>
              <h2>Precision-Recall Curve</h2>
            </div>
            <span className="bm-info-icon" title="Precision vs Recall curve across threshold sweep" aria-label="Precision recall info">
              <Info aria-hidden="true" />
            </span>
          </div>
          <div className="bm-card-body">
            <PrecisionRecallCurve />
          </div>
        </div>

        {/* Card 3: Model Version Comparison */}
        <div className="bm-card">
          <div className="bm-card-header">
            <div className="bm-card-title-group">
              <span className="bm-card-icon bm-icon-blue" aria-hidden="true">
                <FileText />
              </span>
              <h2>Model Version Comparison</h2>
            </div>
            <span className="bm-info-icon" title="Comparison with previous model iteration V6.2" aria-label="Version comparison info">
              <Info aria-hidden="true" />
            </span>
          </div>
          <div className="bm-card-body">
            <VersionComparisonBars />
          </div>
        </div>
      </section>

      {/* Row 3: Bottom Row (Additional Metrics + Test Dataset) */}
      <section className="bm-bottom-grid" aria-label="System Metrics and Dataset Metadata">
        {/* Additional Metrics */}
        <div className="bm-card bm-add-metrics-card">
          <div className="bm-card-header">
            <div className="bm-card-title-group">
              <span className="bm-card-icon bm-icon-blue" aria-hidden="true">
                <FileText />
              </span>
              <h2>Additional Metrics</h2>
            </div>
            <span className="bm-info-icon" title="Runtime, edge performance, and false alert diagnostics" aria-label="Additional metrics info">
              <Info aria-hidden="true" />
            </span>
          </div>
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
              <h2>Test Dataset</h2>
            </div>
          </div>
          <div className="bm-card-body">
            <TestDatasetTable />
          </div>
        </div>
      </section>

      {/* Audit Trail & Detailed Breakdown Card */}
      <section className="bm-card bm-audit-card" aria-label="Audit Trail and Detailed Evidence">
        <div className="bm-card-header bm-audit-card-header">
          <div className="bm-card-title-group">
            <span className="bm-card-icon bm-icon-blue" aria-hidden="true">
              <FileText />
            </span>
            <div>
              <h2>Audit Trail &amp; Detailed Breakdown</h2>
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
                <h3>Results by Activity</h3>
                <span className="bm-subcard-caption">Per-clip classification outcome</span>
              </div>
              <ActivityGrid />
            </div>

            {/* Right: Time to Alert Timeline */}
            <div className="bm-audit-subcard">
              <div className="bm-subcard-header">
                <h3>Time to Alert, Every Detected Fall</h3>
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
