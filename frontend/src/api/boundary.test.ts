import { describe, expect, it } from 'vitest';
import { MockApiClient } from './mockClient.ts';
import { MOCK_CAMERAS, MOCK_INCIDENTS, MOCK_SYSTEM_STATUS } from './mockData.ts';
import { ApiError } from './client.ts';

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
      `/incidents/${encodeURIComponent(detail.id)}/evidence/e-0001`,
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
});
