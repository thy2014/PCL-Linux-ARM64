let token = "";

export function setToken(value) {
  token = value || "";
}

export async function api(path, { method = "GET", body = null } = {}) {
  const headers = {};
  if (body !== null) headers["Content-Type"] = "application/json";
  if (token && method !== "GET") headers["X-PCL-Token"] = token;
  let response;
  try {
    response = await fetch(path, {
      method,
      headers,
      body: body !== null ? JSON.stringify(body) : undefined,
      cache: "no-store",
    });
  } catch (error) {
    throw new Error(`无法连接本地服务：${error.message}`);
  }
  let data = null;
  try {
    data = await response.json();
  } catch {
    data = null;
  }
  if (!response.ok || (data && data.ok === false)) {
    const message = (data && data.error) || `请求失败（HTTP ${response.status}）`;
    const error = new Error(message);
    error.status = response.status;
    throw error;
  }
  return data || { ok: true };
}

export function qs(params) {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") search.set(key, value);
  });
  const text = search.toString();
  return text ? `?${text}` : "";
}
