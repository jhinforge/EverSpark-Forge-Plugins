(() => {
  const words = (en, cn) => document.documentElement.lang.toLowerCase().startsWith("zh") ? cn : en;
  const storageKey = "everspark-lora-catalog-state";
  const filters = {q: "", category: "", model: "", pod: "", notes: "", integrity: "", missingCache: false};
  const defaults = {...filters, sort: "category", pageSize: 50, page: 1, showPreview: true, showOpen: false};
  const fields = ["category", "model_support", "trigger_words", "download_url", "effect", "notes"];
  const value = (field) => Array.isArray(field) ? field.map(value).join(" / ") : String(field ?? "");
  const list = (field, separators) => (Array.isArray(field) ? field : value(field).split(separators)).map(value).map((s) => s.trim()).filter(Boolean);
  const category = (row) => list(row.category, /$/);
  const models = (row) => list(row.model_support, /[/,，、|]/);
  const norm = (field) => value(field).trim().toLowerCase();
  const blank = (field) => Array.isArray(field) ? field.every(blank) : !norm(field);
  const loaded = (row) => norm(row.pod_loaded) === "true";

  function create(tag, label, className) {
    const element = document.createElement(tag);
    if (label) element.textContent = label;
    if (className) element.className = className;
    if (tag === "button") element.type = "button";
    return element;
  }

  function media(row, kind) {
    return "/api/plugins/lora/media?" + new URLSearchParams({id: row.id, kind});
  }

  function attachPicture(parent, row, preferred, description) {
    const alternatives = (preferred === "preview" ? ["preview", "thumbnail"] : ["thumbnail", "preview"])
      .filter((kind) => row[kind]);
    if (!alternatives.length) return;
    const image = create("img");
    image.alt = description;
    if (preferred === "thumbnail") image.loading = "lazy";
    function loadNext() {
      const kind = alternatives.shift();
      if (kind) image.src = media(row, kind);
      else image.remove();
    }
    image.onerror = loadNext;
    parent.append(image);
    loadNext();
  }

  function describe(row) {
    const categories = category(row);
    const support = models(row);
    const marks = loaded(row) ? "pod_loaded pod loaded 当前pod已加载" : "pod_unloaded pod unloaded 当前pod未加载";
    return {
      row, categories, support,
      notes: blank(row.notes) ? "missing" : ["无", "none", "n/a", "na"].includes(norm(row.notes)) ? "none" : "has",
      missing: fields.filter((key) => {
        if (key === "category") return !categories.length;
        if (key === "model_support") return !support.length;
        return blank(row[key]);
      }),
      search: norm([row.title, row.lora_name, row.lora_version, row.effect, row.trigger_words,
        ...support, ...categories, row.download_url, row.notes, marks]),
    };
  }

  function loadState() {
    const state = {...defaults};
    try {
      const saved = JSON.parse(localStorage.getItem(storageKey));
      for (const [key, initial] of Object.entries(defaults)) {
        if (typeof saved?.[key] === typeof initial) state[key] = saved[key];
      }
    } catch (_) { /* Storage may be unavailable. */ }
    return state;
  }

  function mount(root, items) {
    const entries = items.map(describe);
    const state = loadState();
    const compare = (a, b) => a.localeCompare(b, "zh-Hans-CN");
    const stats = create("div", "", "lora-catalog-stats");
    const controls = create("div", "", "lora-catalog-controls");
    const status = create("p", "", "section-copy");
    status.setAttribute("aria-live", "polite");
    const wrapper = create("div", "", "lora-catalog-scroll");
    const table = create("table", "", "lora-catalog-table");
    const header = table.createTHead().insertRow();
    const tbody = table.createTBody();
    wrapper.append(table);
    const pager = create("div", "", "lora-catalog-pager");
    const detail = create("dialog", "", "lora-catalog-dialog");
    detail.setAttribute("aria-label", words("Model details", "模型详情"));
    const hover = create("div", "", "lora-catalog-hover");
    hover.hidden = true;
    hover.setAttribute("aria-hidden", "true");

    let hoverPosition;
    const search = create("input");
    search.type = "search";
    search.placeholder = words("Search models, notes, and trigger words", "搜索模型、备注和触发词");
    search.setAttribute("aria-label", search.placeholder);
    search.value = state.q;
    search.oninput = () => update({q: search.value, missingCache: false});
    controls.append(search);

    const selects = {};
    const choices = (key) => [...new Set(entries.flatMap((entry) => entry[key]))].sort(compare).map((v) => [v, v]);
    function select(key, label, items) {
      const input = create("select");
      input.setAttribute("aria-label", label);
      for (const [id, caption] of items) input.add(new Option(caption, id));
      input.value = state[key];
      if (input.selectedIndex < 0) input.value = defaults[key];
      state[key] = key === "pageSize" ? Number(input.value) : input.value;
      input.onchange = () => update({
        [key]: key === "pageSize" ? Number(input.value) : input.value,
        missingCache: key in filters ? false : state.missingCache,
      });
      selects[key] = input;
      controls.append(input);
    }
    select("category", words("Category", "分类"), [["", words("All categories", "所有分类")], ...choices("categories")]);
    select("model", words("Base model", "支持模型"), [["", words("All base models", "所有支持模型")], ...choices("support")]);
    select("pod", words("Pod status", "Pod 状态"), [
      ["", words("All Pod states", "所有 Pod 状态")], ["loaded", words("Loaded", "已加载")], ["unloaded", words("Not loaded", "未加载")]]);
    select("notes", words("Notes status", "备注状态"), [
      ["", words("All notes", "所有备注")], ["has", words("Has notes", "有备注")],
      ["missing", words("Blank notes", "备注为空")], ["none", words("Explicitly none", "明确标记为无")]]);
    select("integrity", words("Field completeness", "字段完整性"), [
      ["", words("All records", "所有条目")], ["any", words("Any missing field", "任意字段缺失")],
      ["category", words("Missing category", "缺分类")], ["model_support", words("Missing base model", "缺支持模型")],
      ["trigger_words", words("Missing trigger words", "缺触发词")], ["download_url", words("Missing download URL", "缺下载链接")],
      ["effect", words("Missing effect", "缺效果")], ["notes", words("Missing notes", "缺备注")]]);
    select("sort", words("Sort", "排序"), [
      ["category", words("Category, then filename", "按分类、文件名")], ["filename", words("Filename", "按文件名")],
      ["model", words("Base model", "按支持模型")], ["pod", words("Pod loaded first", "Pod 已加载优先")],
      ["newest", words("Recently modified", "最近修改优先")], ["oldest", words("Oldest modified", "最早修改优先")]]);
    select("pageSize", words("Rows per page", "每页条数"), [25, 50, 100].map((size) => [size, String(size)]));

    function toggle(key, caption) {
      const label = create("label", "", "lora-catalog-toggle");
      const input = create("input");
      input.type = "checkbox";
      input.checked = state[key];
      input.onchange = () => {
        state[key] = input.checked;
        render();
      };
      label.append(input, document.createTextNode(caption));
      controls.append(label);
    }
    toggle("showPreview", words("Show previews", "显示预览"));
    toggle("showOpen", words("Show Open column", "显示打开列"));

    const first = create("button", words("First", "首页"), "ghost-button");
    const previous = create("button", words("Previous", "上一页"), "ghost-button");
    const next = create("button", words("Next", "下一页"), "ghost-button");
    const last = create("button", words("Last", "末页"), "ghost-button");
    const pageLabel = create("span");
    pager.append(first, previous, pageLabel, next, last);
    root.replaceChildren(stats, controls, status, wrapper, pager, detail, hover);

    function hideHover() {
      hover.hidden = true;
      hoverPosition = null;
      hover.replaceChildren();
    }

    function show(row) {
      hideHover();
      const heading = create("div", "", "section-toolbar");
      const close = create("button", words("Close", "关闭"), "ghost-button");
      close.onclick = () => detail.close();
      heading.append(create("h3", value(row.lora_name)), close);
      const info = create("dl");
      for (const [key, label] of [
        ["id", words("Note", "笔记")], ["lora_version", words("Version", "版本")],
        ["category", words("Category", "分类")], ["trigger_words", words("Trigger words", "触发词")],
        ["model_support", words("Base model", "支持模型")], ["effect", words("Effect", "效果")],
        ["notes", words("Notes", "备注")], ["download_url", words("Download URL", "下载链接")],
      ]) if (!blank(row[key])) info.append(create("dt", label), create("dd", value(row[key])));
      const source = create("details");
      source.append(create("summary", words("View Markdown", "查看 Markdown 原文")));
      const raw = create("pre");
      source.append(raw);
      source.ontoggle = async () => {
        if (!source.open || raw.dataset.loaded) return;
        raw.dataset.loaded = "true";
        raw.textContent = words("Loading…", "读取中…");
        try {
          const result = await fetch(media(row, "note"), {cache: "no-store"});
          if (!result.ok) throw new Error("Note unavailable");
          raw.textContent = await result.text();
        } catch (_) {
          delete raw.dataset.loaded;
          raw.textContent = words("Could not read this note.", "无法读取该笔记。");
        }
      };
      detail.replaceChildren(heading, info);
      attachPicture(detail, row, "preview", value(row.lora_name));
      detail.append(source);
      detail.showModal();
    }

    function moveHover(event) {
      hoverPosition = event;
      const box = hover.getBoundingClientRect();
      let x = event.clientX + 16;
      if (x + box.width + 12 > window.innerWidth) x = event.clientX - box.width - 16;
      hover.style.left = Math.max(12, x) + "px";
      hover.style.top = Math.max(12, Math.min(event.clientY + 12, window.innerHeight - box.height - 12)) + "px";
    }

    function update(change) {
      Object.assign(state, change, {page: 1});
      search.value = state.q;
      for (const [key, input] of Object.entries(selects)) input.value = state[key];
      render();
    }

    const count = (predicate) => entries.filter(predicate).length;
    const total = entries.length;
    const podCount = count(({row}) => loaded(row));
    const notesCount = count(({notes}) => notes === "has");
    const blankNotes = count(({notes}) => notes === "missing");
    const noneNotes = total - notesCount - blankNotes;
    const incomplete = count(({missing}) => missing.length);
    const cached = count(({row}) => row.thumbnail);
    const noImage = count(({row}) => !(row.image_reference ?? row.preview));

    function card(caption, number, sub, action) {
      const element = create(action ? "button" : "div", "", "lora-catalog-stat");
      element.append(create("span", caption), create("strong", String(number)));
      if (sub) element.append(create("small", sub));
      if (action) element.onclick = action;
      return element;
    }
    const current = card(words("Shown / total", "当前 / 总数"), "", words("Reset filters", "重置筛选"), () => update(filters));
    const cache = card(words("Thumbnail cache", "缩略图缓存"), `${cached} / ${total}`, words(`Missing ${total - cached}`, `缺失 ${total - cached}`),
      cached < total ? () => update({missingCache: !state.missingCache}) : null);
    stats.append(current,
      card(words("Pod loaded", "Pod 已加载"), podCount, words(`Not loaded ${total - podCount}`, `未加载 ${total - podCount}`), () => update({pod: "loaded", missingCache: false})),
      card(words("Has notes", "有备注"), notesCount, words(`Explicitly none ${noneNotes}`, `明确为无 ${noneNotes}`), () => update({notes: "has", missingCache: false})),
      card(words("Blank notes", "备注为空"), blankNotes, "", () => update({notes: "missing", missingCache: false})),
      card(words("Incomplete fields", "字段缺失"), incomplete, "", () => update({integrity: "any", missingCache: false})),
      cache, card(words("No image reference", "无原图引用"), noImage));

    const sortOrders = {
        category: (a, b) => compare(a.categories[0] || "", b.categories[0] || ""),
        filename: () => 0,
        model: (a, b) => compare(value(a.support), value(b.support)),
        pod: (a, b) => Number(loaded(b.row)) - Number(loaded(a.row)),
        newest: (a, b) => (b.row.modified || 0) - (a.row.modified || 0),
        oldest: (a, b) => (a.row.modified || 0) - (b.row.modified || 0),
    };

    function sort(a, b) {
      return sortOrders[state.sort](a, b) || compare(a.row.title, b.row.title) || compare(a.row.id, b.row.id);
    }

    function render() {
      hideHover();
      const terms = norm(state.q).split(/\s+/).filter(Boolean);
      const filtered = entries.filter(({row, categories, support, notes, missing, search}) =>
        (!state.category || categories.includes(state.category)) &&
        (!state.model || support.includes(state.model)) &&
        (!state.pod || loaded(row) === (state.pod === "loaded")) &&
        (!state.notes || notes === state.notes) &&
        (!state.integrity || (state.integrity === "any" ? missing.length : missing.includes(state.integrity))) &&
        (!state.missingCache || !row.thumbnail) &&
        terms.every((term) => search.includes(term))).sort(sort);
      const pages = Math.max(1, Math.ceil(filtered.length / state.pageSize));
      state.page = Math.min(pages, Math.max(1, Math.trunc(state.page)));
      const shown = filtered.slice((state.page - 1) * state.pageSize, state.page * state.pageSize);
      current.querySelector("strong").textContent = `${filtered.length} / ${total}`;
      if (cached < total) cache.setAttribute("aria-pressed", String(state.missingCache));
      status.textContent = filtered.length ? words(`${shown.length} on this page`, `本页 ${shown.length} 个模型`)
        : total ? words("No models match the filters.", "没有符合条件的模型。") : words("No LoRA notes found in this folder.", "所选目录里没有 LoRA 笔记。");

      const columns = [
        ...(state.showPreview ? [words("Preview", "预览")] : []),
        ...(state.showOpen ? [words("Open", "打开")] : []),
        words("Model", "模型"), words("Category", "分类"), words("Base model", "支持模型"),
        words("Pod loaded", "Pod 已加载"), words("Effect", "效果"),
      ];
      header.replaceChildren(...columns.map((caption) => {
        const cell = create("th", caption);
        cell.scope = "col";
        return cell;
      }));
      tbody.replaceChildren();
      for (const {row, categories, support} of shown) {
        const line = tbody.insertRow();
        if (state.showPreview) {
          const cell = line.insertCell();
          if (row.thumbnail || row.preview) {
            const button = create("button", "", "lora-catalog-preview");
            button.setAttribute("aria-label", words("Open ", "打开 ") + value(row.lora_name));
            attachPicture(button, row, "thumbnail", "");
            button.onclick = () => show(row);
            button.onpointerenter = (event) => {
              if (event.pointerType === "touch") return;
              hideHover();
              attachPicture(hover, row, "preview", "");
              const image = hover.querySelector("img");
              image.onload = () => {
                if (hoverPosition && hover.contains(image)) moveHover(hoverPosition);
              };
              hover.hidden = false;
              moveHover(event);
            };
            button.onpointermove = moveHover;
            button.onpointerleave = hideHover;
            cell.append(button);
          } else cell.textContent = "—";
        }
        if (state.showOpen) {
          const open = create("button", row.title, "ghost-button");
          open.onclick = () => show(row);
          line.insertCell().append(open);
        }
        const name = create("button", value(row.lora_name), "ghost-button");
        name.onclick = () => show(row);
        line.insertCell().append(name);
        for (const field of [categories, support, loaded(row) ? words("Loaded", "已加载") : "—", row.effect]) {
          line.insertCell().textContent = value(field) || "—";
        }
      }
      pageLabel.textContent = `${state.page} / ${pages}`;
      first.disabled = previous.disabled = state.page <= 1;
      next.disabled = last.disabled = state.page >= pages;
      last.onclick = () => { state.page = pages; render(); };
      try { localStorage.setItem(storageKey, JSON.stringify(state)); } catch (_) { /* Storage may be unavailable. */ }
    }
    first.onclick = () => { state.page = 1; render(); };
    previous.onclick = () => { state.page--; render(); };
    next.onclick = () => { state.page++; render(); };
    render();
  }

  window.EverSparkLoraCatalog = {
    async mount(root, api) {
      const {items} = await api("/api/plugins/lora/catalog");
      mount(root, items);
    },
  };
})();
