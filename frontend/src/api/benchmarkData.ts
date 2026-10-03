/**
 * Approved static snapshot of the frozen V6.3 evaluation. These are evaluation
 * results, not live metrics. Sources:
 * - docs/reports/V6_3_FINAL_TESTB_EVALUATION.json (sealed Test-B + held-out longform, run once)
 * - docs/reports/V6_FINAL_RESULTS.md (§1 headline, §3 development history)
 * - docs/reports/V6_2_PHASE2_REPORT.md (V6.2 development diagnostics)
 */
export const BENCHMARK = {
  model: 'V6.3', poseModel: 'yolo26s-pose.pt', freezeCommit: 'dbd5756', evaluationCommit: '1f8fd9b',
  dataset: 'UP-Fall Test-B', subjects: '12–17', evaluatedAt: '2026-10-01',
  reportUrl: 'https://github.com/luqshzeeq3601-art/Fall-Detection-Yolo26/blob/main/docs/reports/V6_FINAL_RESULTS.md',
  recall: 98.3, precision: 96.7, medianSeconds: 0.85, p90Seconds: 1.33, p95Seconds: 1.58,
  specificity: 98.6, f1: 0.975,
  truePositives: 59, falseNegatives: 1, adlTrueNegatives: 71, adlFalsePositiveClips: 1,
  falseAlertEvents: 2, fallClips: 60, adlClips: 72, clips: 132,
  recallCi: [91.1, 99.7], precisionCi: [88.8, 99.1], specificityCi: [92.5, 99.8],
  recallInterval: '91.1–99.7%', precisionInterval: '88.8–99.1%',
  gates: { minRecall: 90, minPrecision: 85, maxP95Seconds: 3, maxFalseAlarmsPerHour: 0.05 },
  heldout: { hours: 0.83, falseAlarms: 0, ratePerHour: 0, ci95Upper: 3.59 },
  devLongformRatePerHour: 0.70,
  /** Seconds from annotated fall onset to alert, for each of the 59 detected falls. */
  timeToAlert: [0.593, 0.904, 2.104, 0.506, 1.04, 0.532, 0.598, 0.774, 1.174, 0.741, 0.808, 0.939, 1.072, 0.682, 0.616, 0.478, 0.544, 0.537, 1.07, 0.68, 0.613, 0.622, 0.756, 0.606, 0.606, 0.7, 0.833, 1.148, 1.282, 0.386, 0.586, 0.684, 0.484, 0.487, 0.753, 0.603, 0.67, 0.968, 3.701, 0.846, 0.98, 0.921, 0.921, 0.912, 1.579, 1.043, 1.243, 1.189, 1.256, 0.814, 0.947, 1.193, 1.326, 1.302, 1.435, 1.122, 1.122, 1.219, 1.485],
  /** 12 clips per activity; `correct` = falls alerted, or everyday clips with no alert. */
  activities: [
    { name: 'Forward, onto hands', fall: true, correct: 11, total: 12 },
    { name: 'Forward, onto knees', fall: true, correct: 12, total: 12 },
    { name: 'Backward', fall: true, correct: 12, total: 12 },
    { name: 'Sideways', fall: true, correct: 12, total: 12 },
    { name: 'From a chair', fall: true, correct: 12, total: 12 },
    { name: 'Lying down', fall: false, correct: 11, total: 12 },
    { name: 'Sitting', fall: false, correct: 12, total: 12 },
    { name: 'Picking up', fall: false, correct: 12, total: 12 },
    { name: 'Walking', fall: false, correct: 12, total: 12 },
    { name: 'Standing', fall: false, correct: 12, total: 12 },
    { name: 'Jumping', fall: false, correct: 12, total: 12 },
  ],
  cameras: [
    { name: 'Camera 1', caught: 30, total: 30, p95Seconds: 1.22, falseAlerts: 2 },
    { name: 'Camera 2', caught: 29, total: 30, p95Seconds: 2.10, falseAlerts: 0 },
  ],
  /** Development diagnostics (out-of-fold dev data and the dev-2 Test-X split), not Test-B. */
  history: [
    { version: 'V6.1 audited', note: 'Evaluation leaks removed', cam2Recall: 10, urfdRecall: 47, testXRecall: 2, longformFaPerHour: 4.63 },
    { version: 'V6.2', note: 'Every person tracked, track stitching', cam2Recall: 49, urfdRecall: 87, testXRecall: 30, longformFaPerHour: 0.23 },
    { version: 'V6.3 frozen', note: 'Handover fix, descent posture', cam2Recall: 90, urfdRecall: 97, testXRecall: 87, longformFaPerHour: 0.70 },
  ],
  limitations: [
    'The false-alarm target remains under evaluation: only 0.83 held-out hours were tested.',
    'Test-B contains new recordings of subjects seen in development diagnostics.',
    'Staged falls in one laboratory do not establish performance in real homes.',
  ],
} as const;
