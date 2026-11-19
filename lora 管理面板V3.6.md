```dataviewjs
// =====================================================
// LoRA 管理面板 V3.6
// 功能：
// 1) state 统一管理筛选条件
// 2) 模型筛选 / notes 检查 / 字段完整性检查
// 3) 永久缩略图缓存读取
// 4) 悬浮大图预览
// 5) 默认隐藏“打开”列，点击缩略图也能进入笔记
// 6) 顶部健康统计面板
// 7) 缓存协议固化
// 8) 分页功能：默认每页 50，可切换 25 / 50 / 100
// 9) 缓存缺失卡片可点击筛选
// 10) localStorage 持久化筛选状态，返回总览页时保留筛选/分页
// 11) V3.6：pod_loaded 映射为 Pod；移除已下载/未下载入口；表格列改为 Pod 已加载
// =====================================================


// ====== 可调整：你想显示的列 ======
const COLS = [
  { key: "preview",     name: "预览" },
  { key: "open",        name: "打开" }, // 默认隐藏，可用开关显示
  { key: "category",    name: "分类" },
  { key: "model",       name: "支持模型" },
  { key: "pod",         name: "Pod 已加载" },
  { key: "effect",      name: "效果" },
];


// ====== state：所有筛选/显示/分页条件统一放这里 ======
const state = {
  q: "",
  category: "",
  model: "",
  podStatus: "all",        // all / loaded / unloaded
  notesStatus: "all",      // all / missing / none / has
  integrity: "all",        // all / missing_any / missing_trigger_words / missing_download_url / missing_model_support / missing_notes / missing_effect
  sortBy: "category_name", // category_name / file_name / model / pod_loaded / modified_desc / modified_asc
  showPreview: true,
  showOpen: false,
  page: 1,
  pageSize: 50,
  cacheStatus: "all",     // all / missing，仅用于健康卡片筛选缓存缺失
};

// ====== 状态持久化：返回面板时保留筛选/分页 ======
const STORAGE_KEY = `lora-db-state-v36:${dv.current().file.path}`;

const loadState = () => {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return;
    const saved = JSON.parse(raw);
    Object.assign(state, saved);
  } catch (e) {
    console.warn("LoRA panel state load failed", e);
  }
};

const saveState = () => {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch (e) {
    console.warn("LoRA panel state save failed", e);
  }
};

loadState();


// ====== 读取数据：所有 LoRA 页面 ======
const pages = dv.pages("")
  .where(p => p.lora_name && !p.file.path.startsWith("Checkpoints/"))
  .array();


// ====== 工具函数 ======
const toStr = (v) => {
  if (v === null || v === undefined) return "";
  if (Array.isArray(v)) return v.map(toStr).join(" / ");
  if (typeof v === "object" && v.path) return v.path;
  return String(v);
};

const norm = (s) => toStr(s).toLowerCase().trim();

const isBlank = (v) => {
  if (v === null || v === undefined) return true;
  if (Array.isArray(v)) return v.length === 0 || v.every(x => norm(x) === "");
  return norm(v) === "";
};

const isNotesNone = (p) => {
  const n = norm(p.notes);
  return n === "无" || n === "none" || n === "n/a" || n === "na";
};

const getCategory = (p) => {
  if (Array.isArray(p.category)) return p.category.map(toStr).filter(Boolean);
  const c = toStr(p.category);
  return c ? [c] : [];
};

const getModelList = (p) => {
  if (!p.model_support) return [];

  if (Array.isArray(p.model_support)) {
    return p.model_support.map(toStr).map(s => s.trim()).filter(Boolean);
  }

  return String(p.model_support)
    .split(/[\/，,、|]+/g)
    .map(s => s.trim())
    .filter(Boolean);
};

const getModelSupport = (p) => getModelList(p).join(" / ");
const podMark = (p) => (p.pod_loaded ? "📍" : "⚪");

const fileMTimeMillis = (p) => {
  const m = p.file?.mtime;
  if (!m) return 0;
  if (typeof m.toMillis === "function") return m.toMillis();
  const d = new Date(m);
  return Number.isNaN(d.getTime()) ? 0 : d.getTime();
};


// ====== 图片预览：永久缩略图缓存协议 ======
// 注意：这只影响 temp/lora_thumb_cache 里的缓存图命名，不影响原图归档路径和原图文件名。
// 当前协议：
// md 相对路径：lora/服装/Better_pantyhose.md
// 缓存文件名：Better_pantyhose_<fnv1a32(md相对路径)>.jpg
// 缓存路径：temp/lora_thumb_cache/Better_pantyhose_<hash>.jpg
const THUMB_CACHE_DIR = "temp/lora_thumb_cache";
const THUMB_CACHE_EXT = "jpg";
const IMAGE_EXT_RE = /\.(png|jpe?g|gif|webp|bmp|svg)$/i;
const previewCache = new Map();
const originalPreviewCache = new Map();

const isImagePath = (path) => IMAGE_EXT_RE.test(String(path || "").split("?")[0]);

// 必须和 Python 脚本里的 fnv1a_32() 保持一致
const fnv1a32 = (str) => {
  let h = 0x811c9dc5;
  for (let i = 0; i < str.length; i++) {
    h ^= str.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
  }
  return (h >>> 0).toString(16).padStart(8, "0");
};

const normalizeVaultPath = (path) => String(path || "").replace(/\\/g, "/");

const thumbCacheNameFromMdPath = (mdPath) => {
  const sourcePath = normalizeVaultPath(mdPath);
  if (!sourcePath) return "";
  const stem = sourcePath.split("/").pop().replace(/\.md$/i, "");
  const safeStem = stem.replace(/[\\/:*?"<>|#^\[\]]+/g, "_").slice(0, 80) || "lora";
  return `${safeStem}_${fnv1a32(sourcePath)}.${THUMB_CACHE_EXT}`;
};

const thumbCachePathFromMdPath = (mdPath) => {
  const cacheName = thumbCacheNameFromMdPath(mdPath);
  return cacheName ? `${THUMB_CACHE_DIR}/${cacheName}` : "";
};

const getThumbCachePath = (p) => thumbCachePathFromMdPath(p.file?.path);

const getResourceSrcByVaultPath = (vaultPath) => {
  if (!vaultPath) return "";
  const file = app.vault.getAbstractFileByPath(vaultPath);
  return file ? app.vault.getResourcePath(file) : "";
};

const getOriginalFirstPreviewSrc = (p) => {
  const sourcePath = p.file?.path;
  if (!sourcePath) return "";

  if (originalPreviewCache.has(sourcePath)) return originalPreviewCache.get(sourcePath);

  const sourceFile = app.vault.getAbstractFileByPath(sourcePath);
  const fileCache = sourceFile ? app.metadataCache.getFileCache(sourceFile) : null;
  const embeds = fileCache?.embeds || [];

  for (const embed of embeds) {
    const link = embed?.link || "";
    if (!link) continue;

    const dest = app.metadataCache.getFirstLinkpathDest(link, sourcePath);
    if (dest && isImagePath(dest.path)) {
      const src = app.vault.getResourcePath(dest);
      originalPreviewCache.set(sourcePath, src);
      return src;
    }

    if (isImagePath(link)) {
      originalPreviewCache.set(sourcePath, link);
      return link;
    }
  }

  originalPreviewCache.set(sourcePath, "");
  return "";
};

const getFirstPreviewSrc = (p) => {
  const sourcePath = p.file?.path;
  if (!sourcePath) return "";

  if (previewCache.has(sourcePath)) return previewCache.get(sourcePath);

  const thumbPath = getThumbCachePath(p);
  const cachedSrc = getResourceSrcByVaultPath(thumbPath);
  if (cachedSrc) {
    previewCache.set(sourcePath, cachedSrc);
    return cachedSrc;
  }

  const originalSrc = getOriginalFirstPreviewSrc(p);
  previewCache.set(sourcePath, originalSrc);
  return originalSrc;
};

const hasThumbCache = (p) => {
  const thumbPath = getThumbCachePath(p);
  if (!thumbPath) return false;
  return !!app.vault.getAbstractFileByPath(thumbPath);
};

const hasOriginalPreview = (p) => !!getOriginalFirstPreviewSrc(p);


// ====== 悬浮大图预览 ======
const HOVER_PREVIEW_WIDTH = 420;
const HOVER_PREVIEW_MAX_HEIGHT = 560;
let hoverTimer = null;

const oldHover = document.querySelector(".lora-hover-preview-panel");
if (oldHover) oldHover.remove();

const hoverPanel = document.createElement("div");
hoverPanel.className = "lora-hover-preview-panel";
hoverPanel.style.position = "fixed";
hoverPanel.style.zIndex = "9999";
hoverPanel.style.display = "none";
hoverPanel.style.pointerEvents = "none";
hoverPanel.style.padding = "8px";
hoverPanel.style.borderRadius = "12px";
hoverPanel.style.background = "var(--background-primary)";
hoverPanel.style.border = "1px solid var(--background-modifier-border)";
hoverPanel.style.boxShadow = "0 10px 32px rgba(0,0,0,0.35)";
hoverPanel.style.maxWidth = `${HOVER_PREVIEW_WIDTH + 16}px`;
hoverPanel.style.contain = "layout paint";

const hoverImg = document.createElement("img");
hoverImg.loading = "lazy";
hoverImg.decoding = "async";
hoverImg.style.width = `${HOVER_PREVIEW_WIDTH}px`;
hoverImg.style.maxHeight = `${HOVER_PREVIEW_MAX_HEIGHT}px`;
hoverImg.style.objectFit = "contain";
hoverImg.style.display = "block";
hoverImg.style.borderRadius = "8px";
hoverImg.style.background = "var(--background-secondary)";
hoverPanel.appendChild(hoverImg);
document.body.appendChild(hoverPanel);

const getHoverPreviewSrc = (p) => getOriginalFirstPreviewSrc(p) || getFirstPreviewSrc(p);

const moveHoverPreview = (e) => {
  const gap = 18;
  let left = e.clientX + gap;
  let top = e.clientY + gap;

  const panelWidth = HOVER_PREVIEW_WIDTH + 20;
  const panelHeight = Math.min(HOVER_PREVIEW_MAX_HEIGHT + 20, window.innerHeight - 24);

  if (left + panelWidth > window.innerWidth) left = e.clientX - panelWidth - gap;
  if (top + panelHeight > window.innerHeight) top = window.innerHeight - panelHeight - 12;

  hoverPanel.style.left = `${Math.max(12, left)}px`;
  hoverPanel.style.top = `${Math.max(12, top)}px`;
};

const showHoverPreview = (e, p) => {
  clearTimeout(hoverTimer);
  moveHoverPreview(e);

  hoverTimer = setTimeout(() => {
    const src = getHoverPreviewSrc(p);
    if (!src) return;
    hoverImg.src = src;
    hoverImg.alt = p.file?.name || "preview";
    hoverPanel.style.display = "block";
    moveHoverPreview(e);
  }, 120);
};

const hideHoverPreview = () => {
  clearTimeout(hoverTimer);
  hoverPanel.style.display = "none";
  hoverImg.removeAttribute("src");
};

const makePreviewCell = (p) => {
  const box = document.createElement("div");
  box.classList.add("lora-preview-cell");
  box.style.width = "72px";
  box.style.height = "72px";
  box.style.minWidth = "72px";
  box.style.minHeight = "72px";
  box.style.display = "flex";
  box.style.alignItems = "center";
  box.style.justifyContent = "center";
  box.style.overflow = "hidden";
  box.style.contain = "layout paint size";

  const src = getFirstPreviewSrc(p);

  if (!src) {
    const empty = document.createElement("span");
    empty.textContent = "—";
    empty.style.opacity = "0.45";
    box.appendChild(empty);
    return box;
  }

  const img = document.createElement("img");
  img.src = src;
  img.loading = "lazy";
  img.decoding = "async";
  img.alt = p.file?.name || "preview";
  img.title = p.file?.name || "preview";
  img.style.width = "64px";
  img.style.height = "64px";
  img.style.objectFit = "cover";
  img.style.borderRadius = "8px";
  img.style.flex = "0 0 auto";
  img.style.background = "var(--background-secondary)";
  img.style.display = "block";
  img.style.cursor = "pointer";

  img.onclick = (e) => {
    e.preventDefault();
    hideHoverPreview();
    if (p.file?.path) app.workspace.openLinkText(p.file.path, dv.current().file.path, false);
  };

  img.onmousedown = hideHoverPreview;
  img.onmouseenter = (e) => showHoverPreview(e, p);
  img.onmousemove = moveHoverPreview;
  img.onmouseleave = hideHoverPreview;

  box.appendChild(img);
  return box;
};


// ====== 搜索/字段检查 ======
const searchableText = (p) => {
  const parts = [
    p.file?.name,
    toStr(p.lora_name),
    toStr(p.lora_version),
    toStr(p.effect),
    toStr(p.trigger_words),
    getModelSupport(p),
    ...getCategory(p),
    toStr(p.download_url),
    toStr(p.notes),
    p.pod_loaded ? "pod_loaded pod loaded 当前pod已加载" : "pod_unloaded pod unloaded 当前pod未加载",
  ];
  return norm(parts.join(" | "));
};

const integrityIssues = (p) => {
  const issues = [];
  if (getCategory(p).length === 0) issues.push("缺 category");
  if (getModelList(p).length === 0) issues.push("缺 model_support");
  if (isBlank(p.trigger_words)) issues.push("缺 trigger_words");
  if (isBlank(p.download_url)) issues.push("缺 download_url");
  if (isBlank(p.effect)) issues.push("缺 effect");
  if (isBlank(p.notes)) issues.push("缺 notes");
  return issues;
};

const matchIntegrity = (p) => {
  const issues = integrityIssues(p);
  switch (state.integrity) {
    case "missing_any": return issues.length > 0;
    case "missing_trigger_words": return isBlank(p.trigger_words);
    case "missing_download_url": return isBlank(p.download_url);
    case "missing_model_support": return getModelList(p).length === 0;
    case "missing_notes": return isBlank(p.notes);
    case "missing_effect": return isBlank(p.effect);
    case "all":
    default: return true;
  }
};

const matchNotes = (p) => {
  switch (state.notesStatus) {
    case "missing": return isBlank(p.notes);
    case "none": return isNotesNone(p);
    case "has": return !isBlank(p.notes) && !isNotesNone(p);
    case "all":
    default: return true;
  }
};

const matchPodStatus = (p) => {
  switch (state.podStatus) {
    case "loaded": return !!p.pod_loaded;
    case "unloaded": return !p.pod_loaded;
    case "all":
    default: return true;
  }
};

const matchSearch = (p) => {
  if (!state.q) return true;
  const hay = searchableText(p);
  const terms = state.q.split(/\s+/).filter(Boolean);
  for (const t of terms) if (!hay.includes(t)) return false;
  return true;
};


// ====== UI 元素 ======
const wrap = dv.el("div", "", { cls: "lora-db-wrap" });

const statsArea = wrap.createEl("div", { cls: "lora-db-stats" });
statsArea.style.display = "grid";
statsArea.style.gridTemplateColumns = "repeat(auto-fit, minmax(130px, 1fr))";
statsArea.style.gap = "8px";
statsArea.style.marginBottom = "12px";

const controls = wrap.createEl("div", { cls: "lora-db-controls" });
controls.style.display = "flex";
controls.style.flexWrap = "wrap";
controls.style.gap = "8px 10px";
controls.style.alignItems = "center";
controls.style.marginBottom = "10px";

const qInput = controls.createEl("input", {
  type: "text",
  placeholder: "🔎 搜索：命名/效果/触发词/模型/文件名…",
});
qInput.style.width = "420px";
qInput.style.maxWidth = "100%";
qInput.value = state.q || "";

const catSelect = controls.createEl("select");
catSelect.createEl("option", { text: "🧩 全部分类", value: "" });

const modelSelect = controls.createEl("select");
modelSelect.createEl("option", { text: "🧬 全部模型", value: "" });

const podSelect = controls.createEl("select");
[
  ["all", "📍 全部 Pod 状态"],
  ["loaded", "📍 只看 Pod 已加载"],
  ["unloaded", "⚪ 只看 Pod 未加载"],
].forEach(([value, text]) => podSelect.createEl("option", { value, text }));
podSelect.value = state.podStatus || "all";

const notesSelect = controls.createEl("select");
[
  ["all", "📝 全部 notes"],
  ["missing", "⚠️ notes 为空"],
  ["none", "➖ notes 为无"],
  ["has", "✅ notes 有内容"],
].forEach(([value, text]) => notesSelect.createEl("option", { value, text }));
notesSelect.value = state.notesStatus || "all";

const integritySelect = controls.createEl("select");
[
  ["all", "🧪 全部字段状态"],
  ["missing_any", "⚠️ 任意字段缺失"],
  ["missing_trigger_words", "缺 trigger_words"],
  ["missing_download_url", "缺 download_url"],
  ["missing_model_support", "缺 model_support"],
  ["missing_notes", "缺 notes"],
  ["missing_effect", "缺 effect"],
].forEach(([value, text]) => integritySelect.createEl("option", { value, text }));
integritySelect.value = state.integrity || "all";

const sortSelect = controls.createEl("select");
[
  ["category_name", "排序：分类 + 文件名"],
  ["file_name", "排序：文件名"],
  ["model", "排序：支持模型"],
  ["pod_loaded", "排序：Pod 已加载"],
  ["modified_desc", "排序：最近修改优先"],
  ["modified_asc", "排序：最早修改优先"],
].forEach(([value, text]) => sortSelect.createEl("option", { value, text }));
sortSelect.value = state.sortBy || "category_name";

const pageSizeSelect = controls.createEl("select");
[
  ["25", "每页 25"],
  ["50", "每页 50"],
  ["100", "每页 100"],
].forEach(([value, text]) => pageSizeSelect.createEl("option", { value, text }));
pageSizeSelect.value = String(state.pageSize);

const previewLabel = controls.createEl("label", { text: "🖼️ 显示预览" });
previewLabel.style.display = "inline-flex";
previewLabel.style.alignItems = "center";
previewLabel.style.gap = "6px";
previewLabel.style.userSelect = "none";
const previewToggle = controls.createEl("input", { type: "checkbox" });
previewToggle.checked = state.showPreview;
previewLabel.prepend(previewToggle);

const openLabel = controls.createEl("label", { text: "🔗 显示打开列" });
openLabel.style.display = "inline-flex";
openLabel.style.alignItems = "center";
openLabel.style.gap = "6px";
openLabel.style.userSelect = "none";
const openToggle = controls.createEl("input", { type: "checkbox" });
openToggle.checked = state.showOpen;
openLabel.prepend(openToggle);

const countEl = controls.createEl("span");
countEl.style.marginLeft = "4px";
countEl.style.opacity = "0.85";

const pager = controls.createEl("div", { cls: "lora-db-pager" });
pager.style.display = "inline-flex";
pager.style.alignItems = "center";
pager.style.gap = "6px";
pager.style.marginLeft = "4px";
const firstBtn = pager.createEl("button", { text: "首页" });
const prevBtn = pager.createEl("button", { text: "上一页" });
const pageInfo = pager.createEl("span", { text: "第 1 / 1 页" });
pageInfo.style.opacity = "0.85";
const nextBtn = pager.createEl("button", { text: "下一页" });
const lastBtn = pager.createEl("button", { text: "末页" });

const catSet = new Set();
for (const p of pages) for (const c of getCategory(p)) if (c) catSet.add(c);
[...catSet].sort((a,b)=>a.localeCompare(b,"zh-Hans-CN")).forEach(c => {
  catSelect.createEl("option", { text: c, value: c });
});
catSelect.value = state.category || "";

const modelSet = new Set();
for (const p of pages) for (const m of getModelList(p)) if (m) modelSet.add(m);
[...modelSet].sort((a,b)=>a.localeCompare(b,"zh-Hans-CN")).forEach(m => {
  modelSelect.createEl("option", { text: m, value: m });
});
modelSelect.value = state.model || "";

const resultArea = wrap.createEl("div", { cls: "lora-db-result" });


// ====== 渲染函数 ======
let lastTimer = null;

const makeStatCard = ({ label, value, sub = "", action = null, accent = false }) => {
  const card = statsArea.createEl("div", { cls: "lora-stat-card" });
  card.style.padding = "10px 12px";
  card.style.borderRadius = "12px";
  card.style.background = accent ? "var(--background-modifier-hover)" : "var(--background-secondary)";
  card.style.border = "1px solid var(--background-modifier-border)";
  card.style.minHeight = "64px";
  card.style.boxSizing = "border-box";
  card.style.display = "flex";
  card.style.flexDirection = "column";
  card.style.justifyContent = "center";
  card.style.gap = "4px";

  if (action) {
    card.style.cursor = "pointer";
    card.title = "点击应用对应筛选";
    card.onclick = action;
  }

  const top = card.createEl("div", { text: label });
  top.style.fontSize = "12px";
  top.style.opacity = "0.78";

  const mid = card.createEl("div", { text: String(value) });
  mid.style.fontSize = "22px";
  mid.style.fontWeight = "700";
  mid.style.lineHeight = "1.1";

  if (sub) {
    const bottom = card.createEl("div", { text: sub });
    bottom.style.fontSize = "11px";
    bottom.style.opacity = "0.68";
    bottom.style.whiteSpace = "nowrap";
    bottom.style.overflow = "hidden";
    bottom.style.textOverflow = "ellipsis";
  }
};

const resetPage = () => { state.page = 1; };

const applySelect = (selectEl, value, stateKey) => {
  state[stateKey] = value;
  selectEl.value = value;
  state.cacheStatus = "all";
  resetPage();
  hideHoverPreview();
  render();
};

const applyCacheMissingFilter = () => {
  state.cacheStatus = "missing";
  resetPage();
  hideHoverPreview();
  render();
};

const resetResultFilters = () => {
  state.q = "";
  state.category = "";
  state.model = "";
  state.podStatus = "all";
  state.notesStatus = "all";
  state.integrity = "all";
  state.cacheStatus = "all";
  state.page = 1;

  qInput.value = "";
  catSelect.value = "";
  modelSelect.value = "";
  podSelect.value = "all";
  notesSelect.value = "all";
  integritySelect.value = "all";

  hideHoverPreview();
  render();
};

function renderStats(filtered) {
  statsArea.replaceChildren();

  const total = pages.length;
  const current = filtered.length;
  const podLoaded = pages.filter(p => !!p.pod_loaded).length;
  const podUnloaded = total - podLoaded;
  const notesMissing = pages.filter(p => isBlank(p.notes)).length;
  const notesNone = pages.filter(p => isNotesNone(p)).length;
  const notesHas = pages.filter(p => !isBlank(p.notes) && !isNotesNone(p)).length;
  const integrityMissing = pages.filter(p => integrityIssues(p).length > 0).length;
  const cacheHit = pages.filter(p => hasThumbCache(p)).length;
  const cacheMissing = total - cacheHit;
  const noImage = pages.filter(p => !hasOriginalPreview(p)).length;

  makeStatCard({
    label: "📦 当前 / 总数",
    value: `${current} / ${total}`,
    sub: current === total ? "未启用结果筛选" : "点击恢复全量视图",
    accent: true,
    action: resetResultFilters,
  });

  makeStatCard({
    label: "📍 Pod 已加载",
    value: podLoaded,
    sub: `未加载 ${podUnloaded}，点击只看已加载`,
    action: () => applySelect(podSelect, "loaded", "podStatus"),
  });
  makeStatCard({ label: "📝 notes 有内容", value: notesHas, sub: `为空 ${notesMissing} / 为无 ${notesNone}`, action: () => applySelect(notesSelect, "has", "notesStatus") });
  makeStatCard({ label: "⚠️ notes 为空", value: notesMissing, sub: "点击筛出待补 notes", action: () => applySelect(notesSelect, "missing", "notesStatus") });
  makeStatCard({ label: "🧪 字段缺失", value: integrityMissing, sub: "任意关键字段缺失", action: () => applySelect(integritySelect, "missing_any", "integrity") });
  makeStatCard({
    label: "🖼️ 缩略图缓存",
    value: `${cacheHit} / ${total}`,
    sub: cacheMissing ? `缺失 ${cacheMissing}，点击筛出` : "缓存完整",
    action: cacheMissing ? applyCacheMissingFilter : null,
  });
  makeStatCard({ label: "🚫 无原图引用", value: noImage, sub: "md 内未检测到图片嵌入" });
}

function renderTable(headers, rows, visibleCols) {
  resultArea.replaceChildren();

  const table = resultArea.createEl("table", { cls: "dataview table-view-table" });
  table.style.width = "100%";
  table.style.tableLayout = state.showPreview ? "fixed" : "auto";

  const thead = table.createEl("thead");
  const trh = thead.createEl("tr");
  headers.forEach((h, idx) => {
    const th = trh.createEl("th", { text: h });
    if (visibleCols?.[idx]?.key === "preview") th.style.width = "84px";
  });

  const tbody = table.createEl("tbody");
  for (const r of rows) {
    const tr = tbody.createEl("tr");
    for (const cell of r) {
      const td = tr.createEl("td");
      td.style.verticalAlign = "middle";
      if (state.showPreview && cell instanceof HTMLElement && cell.classList?.contains("lora-preview-cell")) {
        td.style.width = "84px";
        td.style.minWidth = "84px";
      }

      if (cell && typeof cell === "object" && cell.path) {
        let name = cell.path.split("/").pop().replace(/\.md$/, "");
        const a = td.createEl("a", { text: name });
        a.href = "#";
        a.onclick = (e) => {
          e.preventDefault();
          hideHoverPreview();
          app.workspace.openLinkText(cell.path, dv.current().file.path, false);
        };
      } else if (cell instanceof HTMLElement) {
        td.appendChild(cell);
      } else {
        td.setText(String(cell ?? ""));
      }
    }
  }
}

function sortPages(items) {
  return items.sort((a, b) => {
    if (state.sortBy === "file_name") {
      return (a.file?.name || "").localeCompare((b.file?.name || ""), "zh-Hans-CN");
    }

    if (state.sortBy === "model") {
      const mcmp = getModelSupport(a).localeCompare(getModelSupport(b), "zh-Hans-CN");
      if (mcmp !== 0) return mcmp;
      return (a.file?.name || "").localeCompare((b.file?.name || ""), "zh-Hans-CN");
    }

    if (state.sortBy === "pod_loaded") {
      const ad = a.pod_loaded ? 1 : 0;
      const bd = b.pod_loaded ? 1 : 0;
      if (ad !== bd) return bd - ad; // Pod 已加载排前面
      return (a.file?.name || "").localeCompare((b.file?.name || ""), "zh-Hans-CN");
    }

    if (state.sortBy === "modified_desc") return fileMTimeMillis(b) - fileMTimeMillis(a);
    if (state.sortBy === "modified_asc") return fileMTimeMillis(a) - fileMTimeMillis(b);

    const ac = getCategory(a)[0] || "";
    const bc = getCategory(b)[0] || "";
    const ccmp = ac.localeCompare(bc, "zh-Hans-CN");
    if (ccmp !== 0) return ccmp;
    return (a.file?.name || "").localeCompare((b.file?.name || ""), "zh-Hans-CN");
  });
}

function getFilteredPages() {
  return pages.filter(p => {
    if (!matchPodStatus(p)) return false;

    if (state.category) {
      const cats = getCategory(p);
      if (!cats.includes(state.category)) return false;
    }

    if (state.model) {
      const models = getModelList(p);
      if (!models.includes(state.model)) return false;
    }

    if (!matchNotes(p)) return false;
    if (!matchIntegrity(p)) return false;
    if (!matchSearch(p)) return false;
    if (state.cacheStatus === "missing" && hasThumbCache(p)) return false;

    return true;
  });
}

function render() {
  const filtered = getFilteredPages();
  renderStats(filtered);

  const sorted = sortPages([...filtered]);
  const totalPages = Math.max(1, Math.ceil(sorted.length / state.pageSize));
  if (state.page > totalPages) state.page = totalPages;
  if (state.page < 1) state.page = 1;

  const start = (state.page - 1) * state.pageSize;
  const end = start + state.pageSize;
  const paged = sorted.slice(start, end);

  pageInfo.textContent = `第 ${state.page} / ${totalPages} 页`;
  firstBtn.disabled = state.page <= 1;
  prevBtn.disabled = state.page <= 1;
  nextBtn.disabled = state.page >= totalPages;
  lastBtn.disabled = state.page >= totalPages;
  countEl.textContent = `📦 ${filtered.length} / ${pages.length}（本页 ${paged.length}）`;

  const visibleCols = COLS.filter(c => {
    if (c.key === "preview" && !state.showPreview) return false;
    if (c.key === "open" && !state.showOpen) return false;
    return true;
  });

  const headers = visibleCols.map(c => c.name);
  const rows = paged.map(p => visibleCols.map(col => {
    if (col.key === "preview") return makePreviewCell(p);
    if (col.key === "open") return p.file.link;
    if (col.key === "category") return getCategory(p).join(" / ");
    if (col.key === "model") return getModelSupport(p);
    if (col.key === "pod") return podMark(p);
    return p[col.key] ?? "";
  }));

  renderTable(headers, rows, visibleCols);
  saveState();
}

function scheduleRender() {
  if (lastTimer) clearTimeout(lastTimer);
  lastTimer = setTimeout(render, 80);
}


// ====== 事件绑定 ======
qInput.oninput = () => {
  state.q = norm(qInput.value);
  state.cacheStatus = "all";
  resetPage();
  scheduleRender();
};

catSelect.onchange = () => { state.category = catSelect.value; state.cacheStatus = "all"; resetPage(); render(); };
modelSelect.onchange = () => { state.model = modelSelect.value; state.cacheStatus = "all"; resetPage(); render(); };
podSelect.onchange = () => { state.podStatus = podSelect.value; state.cacheStatus = "all"; resetPage(); render(); };
notesSelect.onchange = () => { state.notesStatus = notesSelect.value; state.cacheStatus = "all"; resetPage(); render(); };
integritySelect.onchange = () => { state.integrity = integritySelect.value; state.cacheStatus = "all"; resetPage(); render(); };
sortSelect.onchange = () => { state.sortBy = sortSelect.value; resetPage(); render(); };

pageSizeSelect.onchange = () => {
  state.pageSize = Number(pageSizeSelect.value) || 50;
  resetPage();
  hideHoverPreview();
  render();
};

firstBtn.onclick = () => { hideHoverPreview(); state.page = 1; render(); };
prevBtn.onclick = () => { hideHoverPreview(); state.page = Math.max(1, state.page - 1); render(); };
nextBtn.onclick = () => { hideHoverPreview(); state.page = state.page + 1; render(); };
lastBtn.onclick = () => {
  hideHoverPreview();
  const totalPages = Math.max(1, Math.ceil(getFilteredPages().length / state.pageSize));
  state.page = totalPages;
  render();
};

previewToggle.onchange = () => {
  state.showPreview = previewToggle.checked;
  hideHoverPreview();
  render();
};

openToggle.onchange = () => {
  state.showOpen = openToggle.checked;
  hideHoverPreview();
  render();
};

// 首次渲染
render();
```
