const BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

class ApiError extends Error {
  constructor(status, detail) {
    super(typeof detail === "string" ? detail : JSON.stringify(detail));
    this.status = status;
    this.detail = detail;
  }
}

async function request(path, { method = "GET", body, token, params } = {}) {
  let url = `${BASE_URL}${path}`;
  if (params) {
    const qs = new URLSearchParams(
      Object.fromEntries(Object.entries(params).filter(([, v]) => v !== undefined && v !== ""))
    ).toString();
    if (qs) url += `?${qs}`;
  }

  const headers = { "Content-Type": "application/json" };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(url, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });

  if (!res.ok) {
    let detail;
    try {
      detail = (await res.json()).detail;
    } catch {
      detail = res.statusText;
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return null;
  return res.json();
}

export const api = {
  login: (email, password) => request("/auth/login", { method: "POST", body: { email, password } }),
  me: (token) => request("/auth/me", { token }),

  submitApplication: (token, payload) =>
    request("/applications", { method: "POST", body: payload, token }),
  predict: (token, applicationId) =>
    request(`/predict/${applicationId}`, { method: "POST", token }),
  explain: (token, predictionId) => request(`/explain/${predictionId}`, { token }),
  whatIf: (token, applicationId, payload) =>
    request(`/whatif/${applicationId}`, { method: "POST", body: payload, token }),

  fairnessReports: (token) => request("/admin/fairness-reports", { token }),
  driftReports: (token) => request("/admin/drift-reports", { token }),
  modelVersions: (token) => request("/admin/model-versions", { token }),
  activateModel: (token, modelVersionId, approvedBy) =>
    request(`/admin/model-versions/${modelVersionId}/activate`, {
      method: "POST",
      body: { approved_by: approvedBy },
      token,
    }),
  auditLogs: (token, params) => request("/admin/audit-logs", { token, params }),
};

export { ApiError };
