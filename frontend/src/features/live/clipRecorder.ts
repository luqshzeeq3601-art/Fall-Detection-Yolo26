/** Record `seconds` of an <img> MJPEG stream to a WebM file via a canvas. */
export async function recordImageClip(img: HTMLImageElement, seconds: number, fileName: string, signal?: AbortSignal): Promise<void> {
  if (typeof MediaRecorder === 'undefined') throw new Error('Clip recording is not supported in this browser.');
  const width = img.naturalWidth || 640;
  const height = img.naturalHeight || 480;
  const canvas = document.createElement('canvas');
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext('2d');
  if (!ctx) throw new Error('Canvas is unavailable.');
  const stream = canvas.captureStream(15);
  const mime = ['video/webm;codecs=vp9', 'video/webm;codecs=vp8', 'video/webm'].find((type) => MediaRecorder.isTypeSupported(type));
  const recorder = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
  const chunks: Blob[] = [];
  recorder.ondataavailable = (event) => { if (event.data.size > 0) chunks.push(event.data); };
  const draw = window.setInterval(() => ctx.drawImage(img, 0, 0, width, height), 1000 / 15);
  const done = new Promise<void>((resolve) => { recorder.onstop = () => resolve(); });
  recorder.start(500);
  await new Promise<void>((resolve) => {
    const timer = window.setTimeout(resolve, seconds * 1000);
    signal?.addEventListener('abort', () => { window.clearTimeout(timer); resolve(); }, { once: true });
  });
  recorder.stop();
  await done;
  window.clearInterval(draw);
  stream.getTracks().forEach((track) => track.stop());
  if (signal?.aborted) throw new DOMException('Recording cancelled', 'AbortError');
  const link = document.createElement('a');
  link.href = URL.createObjectURL(new Blob(chunks, { type: 'video/webm' }));
  link.download = fileName;
  link.click();
  window.setTimeout(() => URL.revokeObjectURL(link.href), 1000);
}
