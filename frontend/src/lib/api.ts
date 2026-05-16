const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

export const ADMIN_TOKEN = import.meta.env.VITE_ADMIN_ACCESS_TOKEN || '';

async function errorMessage(response: Response): Promise<string> {
  const text = await response.text();
  if (!text) return 'Request failed';
  try {
    const data = JSON.parse(text);
    const detail = data?.detail;
    if (Array.isArray(detail)) {
      return detail[0]?.msg || 'Request failed';
    }
    return detail || data?.message || text;
  } catch {
    return text;
  }
}

export async function apiPost<T>(path: string, payload: unknown, headers?: Record<string, string>): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...(headers || {}) },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(await errorMessage(response));
  }
  return response.json();
}

export async function apiPatch<T>(path: string, payload: unknown, headers?: Record<string, string>): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json', ...(headers || {}) },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(await errorMessage(response));
  }
  return response.json();
}

export async function apiDelete<T>(path: string, headers?: Record<string, string>): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: 'DELETE',
    headers,
  });
  if (!response.ok) {
    throw new Error(await errorMessage(response));
  }
  return response.json();
}

export async function apiPostForm<T>(path: string, payload: FormData): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    body: payload,
  });
  if (!response.ok) {
    throw new Error(await errorMessage(response));
  }
  return response.json();
}

export async function apiGet<T>(path: string, headers?: Record<string, string>): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, { headers });
  if (!response.ok) {
    throw new Error(await errorMessage(response));
  }
  return response.json();
}

export async function checkHealth(): Promise<void> {
  const response = await fetch(`${API_BASE}/health`);
  if (!response.ok) {
    throw new Error('Health check failed');
  }
}
