import { Home } from 'lucide-react';
import { useEffect, useState, type JSX } from 'react';
import { incidentApi, type RealWorldAccuracy } from '../../api/platform.ts';

const WINDOWS = [7, 30, 90] as const;

/**
 * How detection is doing in the rooms it actually watches, judged by reviewers'
 * decisions. Complements the frozen lab evaluation below it; video analysis is excluded.
 */
export function FieldAccuracy(): JSX.Element {
  const [days, setDays] = useState<(typeof WINDOWS)[number]>(30);
  const [data, setData] = useState<RealWorldAccuracy | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    let cancelled = false;
    incidentApi.accuracy(days)
      .then((value) => { if (!cancelled) { setData(value); setError(''); } })
      .catch(() => { if (!cancelled) setError('Results from your rooms are unavailable right now.'); });
    return () => { cancelled = true; };
  }, [days]);

  const reviewed = data ? data.real_falls + data.false_alarms + data.unsure : 0;
  return (
    <section className="bm-card bm-field-card" aria-labelledby="bm-field-title">
      <div className="bm-card-header">
        <div className="bm-card-title-group">
          <span className="bm-card-icon bm-icon-blue" aria-hidden="true"><Home /></span>
          <h2 id="bm-field-title">In your rooms</h2>
        </div>
        <label className="bm-field-window">
          <span className="sr-only">Period</span>
          <select value={days} onChange={(event) => setDays(Number(event.target.value) as (typeof WINDOWS)[number])}>
            {WINDOWS.map((value) => <option key={value} value={value}>Last {value} days</option>)}
          </select>
        </label>
      </div>
      <p className="bm-card-caption">Alerts from your cameras, judged by your team&apos;s review decisions. Video analysis is not counted.</p>
      {error ? <p className="helper" role="status">{error}</p> : !data ? <p className="helper">Loading…</p> : data.alerts === 0 ? (
        <p className="helper">No alerts from your cameras in the last {data.days} days.</p>
      ) : (
        <>
          <dl className="bm-field-stats">
            <div><dt>Alerts</dt><dd>{data.alerts}</dd></div>
            <div><dt>Real falls</dt><dd>{data.real_falls}</dd></div>
            <div><dt>False alarms</dt><dd>{data.false_alarms}</dd></div>
            <div><dt>Alerts that were real falls</dt><dd>{data.precision === null ? '—' : `${Math.round(data.precision * 100)}%`}</dd></div>
            <div><dt>False alarms per day</dt><dd>{data.false_alarms_per_day.toFixed(2)}</dd></div>
          </dl>
          {data.not_reviewed > 0 ? <p className="helper">{data.not_reviewed} of {data.alerts} alerts are not reviewed yet{reviewed ? ', so these figures may change' : ''}.</p> : null}
          <table className="bm-field-table">
            <caption className="sr-only">Alerts by camera</caption>
            <thead><tr><th scope="col">Camera</th><th scope="col">Alerts</th><th scope="col">Real falls</th><th scope="col">False alarms</th><th scope="col">Unsure</th><th scope="col">Not reviewed</th></tr></thead>
            <tbody>
              {data.cameras.map((camera) => (
                <tr key={camera.camera_id}><th scope="row">{camera.name}</th><td>{camera.alerts}</td><td>{camera.real_falls}</td><td>{camera.false_alarms}</td><td>{camera.unsure}</td><td>{camera.not_reviewed}</td></tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </section>
  );
}
