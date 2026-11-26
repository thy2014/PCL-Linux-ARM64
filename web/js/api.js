let token = "";

export function setToken(value) {
  token = value || "";
}

export async function api(path, { method = "GET", body = null, timeout = 0 } = {}) {
  const headers = {};
  if (body !== null) headers["Content-Type"] = "application/json";
  if (token && method !== "GET") headers["X-PCL-Token"] = token;
  const controller = timeout > 0 && typeof AbortController !== "undefined" ? new AbortController() : null;
  const timer = controller ? setTimeout(() => controller.abort(), timeout) : 0;
  let response;
  try {
    response = await fetch(path, {
      method,
      headers,
      body: body !== null ? JSON.stringify(body) : undefined,
      cache: "no-store",
      signal: controller?.signal,
    });
  } catch (error) {
    if (error?.name === "AbortError") {
      throw new Error(`请求超时：加载器元数据服务器没有响应（${Math.round(timeout / 1000)} 秒）`);
    }
    throw new Error(`无法连接本地服务：${error.message}`);
  } finally {
    if (timer) clearTimeout(timer);
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
