const buffers = new Map<string, Promise<ArrayBuffer>>();

async function download(url: string, onProgress?: (fraction: number) => void): Promise<ArrayBuffer> {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`${url}: HTTP ${response.status}`);
  const total = Number(response.headers.get('content-length')) || 0;
  if (!response.body || !total || !onProgress) return response.arrayBuffer();

  const reader = response.body.getReader();
  const chunks: Uint8Array[] = [];
  let received = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    chunks.push(value);
    received += value.length;
    onProgress(Math.min(1, received / total));
  }
  const bytes = new Uint8Array(received);
  let offset = 0;
  for (const chunk of chunks) {
    bytes.set(chunk, offset);
    offset += chunk.length;
  }
  return bytes.buffer;
}

/** Downloads a file once per session; later calls reuse the same bytes. */
export function fetchBuffer(url: string, onProgress?: (fraction: number) => void): Promise<ArrayBuffer> {
  const cached = buffers.get(url);
  if (cached) {
    if (onProgress) void cached.then(() => onProgress(1));
    return cached;
  }
  const pending = download(url, onProgress);
  buffers.set(url, pending);
  pending.catch(() => buffers.delete(url));
  return pending;
}
