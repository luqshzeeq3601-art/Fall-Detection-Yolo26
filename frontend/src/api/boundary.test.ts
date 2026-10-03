import { describe, expect, it, vi } from 'vitest';
import { MockApiClient } from './mockClient.ts';
import { MOCK_CAMERAS, MOCK_INCIDENTS, MOCK_SYSTEM_STATUS } from './mockData.ts';
import { ApiError, HttpApiClient } from './client.ts';

const FORBIDDEN = ['rtsp', 'password', 'secret', 'token', 'stack', 'traceback'];

function serialized(value: unknown): string {
  return JSON.stringify(value).toLowerCase();
}

describe('P6-001 API boundary mirrors Phase 5 contracts', () => {
  it('camera shapes contain exactly the backend CameraRead fields', () => {
    for (const camera of MOCK_CAMERAS) {
      expect(Object.keys(camera).sort()).toEqual(
        ['id', 'last_frame_at', 'last_heartbeat_at', 'name', 'reconnect_count', 'status'].sort(),
      );
    }
  });

  it('system status contains required Phase 5 fields only', () => {
    expect(Object.keys(MOCK_SYSTEM_STATUS).sort()).toEqual(
      [
        'camera_count',
        'config_version',
        'gpu_summary',
        'inference_latency_ms',
        'integrations',
        'model_name',
        'model_version',
        'version',
        'vision_fps',
      ].sort(),
    );
    expect(MOCK_SYSTEM_STATUS.model_name).toBe('yolo26s-pose.pt');
  });

  it('incident summaries preserve detector fields and immutability inputs', () => {
    for (const incident of MOCK_INCIDENTS) {
      expect(incident.model_name).toBe('yolo26s-pose.pt');
      expect(typeof incident.fall_score).toBe('number');
      expect(incident.detector_state).toBe('FALL_CONFIRMED');
      expect(Array.isArray(incident.evidence)).toBe(true);
      expect(Array.isArray(incident.reviews)).toBe(true);
    }
  });

  it('exposes no RTSP URLs, credentials, or stack traces', () => {
    const blob = serialized({ MOCK_CAMERAS, MOCK_INCIDENTS, MOCK_SYSTEM_STATUS });
    for (const word of FORBIDDEN) {
      expect(blob).not.toContain(word);
    }
  });

  it('mock client supports success paths deterministically', async () => {
    const client = new MockApiClient();
    await expect(client.getHealth()).resolves.toEqual({ status: 'ok' });
    await expect(client.listCameras()).resolves.toHaveLength(3);
    await expect(
      client.getCamera('cam-01'),
    ).resolves.toMatchObject({ id: 'cam-01', name: 'Hallway Camera' });
    const page = await client.listIncidents({ limit: 50, offset: 0 });
    expect(page.total).toBe(3);
    expect(page.items).toHaveLength(3);
    const detail = await client.getIncident(MOCK_INCIDENTS[0].id);
    expect(detail.evidence).toHaveLength(1);
    expect(client.evidenceUrl(detail.id, 'e-0001')).toBe(
      '/demo-evidence.svg',
    );
  });

  it('mock client raises typed 404s for unknown ids', async () => {
    const client = new MockApiClient();
    await expect(client.getCamera('nope')).rejects.toMatchObject({ code: 'CAMERA_NOT_FOUND' });
    await expect(client.getIncident('nope')).rejects.toMatchObject({
      code: 'INCIDENT_NOT_FOUND',
    });
  });

  it('mock client enforces review label allowlist + notes length', async () => {
    const client = new MockApiClient();
    const id = MOCK_INCIDENTS[0].id;
    await expect(
      client.submitReview(id, { label: 'confirmed_fall', notes: 'ok' }),
    ).resolves.toMatchObject({ label: 'confirmed_fall' });
    await expect(
      // @ts-expect-error - invalid label must be rejected at runtime
      client.submitReview(id, { label: 'fake' }),
    ).rejects.toMatchObject({ code: 'INVALID_REVIEW_LABEL' });
    await expect(
      client.submitReview(id, { label: 'non_fall', notes: 'x'.repeat(2001) }),
    ).rejects.toBeInstanceOf(ApiError);
  });

  it('mock client supports failure modes needed by UI tests', async () => {
    const client = new MockApiClient();
    client.setFailureMode('cameras');
    await expect(client.listCameras()).rejects.toBeInstanceOf(ApiError);
    client.setFailureMode('none');
    await expect(client.listCameras()).resolves.toHaveLength(3);
  });

  it('filters incidents by camera without inventing fields', async () => {
    const client = new MockApiClient();
    const page = await client.listIncidents({ camera_id: 'cam-01' });
    expect(page.total).toBe(2);
    expect(page.items.every((i) => i.camera_id === 'cam-01')).toBe(true);
  });

  it('filters the review queue by completed enrichment verdict and absent reviews', async () => {
    const client = new MockApiClient();
    const page = await client.listIncidents({ needs_review: true });
    expect(page.total).toBe(2);
    expect(page.items.map((incident) => incident.id)).toEqual([
      MOCK_INCIDENTS[0].id,
      MOCK_INCIDENTS[2].id,
    ]);
  });

  it('filters from and to inclusively, orders by confirmed time, then applies offset', async () => {
    const client = new MockApiClient();
    const page = await client.listIncidents({
      from: '2026-09-23T06:40:06Z',
      to: '2026-09-23T07:10:04Z',
      limit: 1,
      offset: 1,
    });
    expect(page.total).toBe(2);
    expect(page.items).toHaveLength(1);
    expect(page.items[0].id).toBe(MOCK_INCIDENTS[1].id);
    expect(page.items[0].confirmed_at).toBe('2026-09-23T06:40:06Z');
  });

  it('serializes needs_review and date filters for the HTTP boundary', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      text: async () => JSON.stringify({ items: [], total: 0, limit: 50, offset: 0 }),
    });
    vi.stubGlobal('fetch', fetchMock);
    const client = new HttpApiClient('/api');

    await client.listIncidents({
      needs_review: true,
      from: '2026-09-23T06:00:00Z',
      to: '2026-09-23T07:00:00Z',
    });

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/incidents?needs_review=true&from=2026-09-23T06%3A00%3A00Z&to=2026-09-23T07%3A00%3A00Z',
      expect.objectContaining({ headers: { 'Content-Type': 'application/json' } }),
    );
  });

  it('only resolves evidence IDs owned by the requested incident', () => {
    const client = new MockApiClient();
    const firstId = MOCK_INCIDENTS[0].id;
    const secondId = MOCK_INCIDENTS[1].id;
    expect(client.evidenceUrl(firstId, 'e-0001')).toBe('/demo-evidence.svg');
    expect(() => client.evidenceUrl(firstId, 'missing')).toThrowError(ApiError);
    expect(() => client.evidenceUrl(secondId, 'e-0001')).toThrowError(ApiError);
  });
});
