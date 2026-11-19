(() => {
  const zh = () => document.documentElement.lang.toLowerCase().startsWith("zh");
  const words = (en, cn) => zh() ? cn : en;
  const create = (tag, label, className) => {
    const element = document.createElement(tag);
    if (label) element.textContent = label;
    if (className) element.className = className;
    return element;
  };
  const value = (field) => Array.isArray(field) ? field.join(" / ") : String(field ?? "");
  const yes = (field) => String(field).toLowerCase() === "true";
  const picture = (row, kind) => "/api/plugins/lora/media?" + new URLSearchParams({id: row.id, kind});

  function attachPicture(parent, row, preferred, description) {
    const alternatives = (preferred === "preview" ? ["preview", "thumbnail"] : ["thumbnail", "preview"])
      .filter((kind) => row[kind]);
    if (!alternatives.length) return;
    const image = create("img");
    image.alt = description;
    if (preferred === "thumbnail") image.loading = "lazy";
    function loadNext() {
      const kind = alternatives.shift();
      if (kind) image.src = picture(row, kind);
      else image.remove();
    }
    image.onerror = loadNext;
    parent.append(image);
    loadNext();
  }

  window.EverSparkLoraCatalog = {
    async mount(root, api) {
      const {items} = await api("/api/plugins/lora/catalog");
      const controls = create("div", "", "lora-catalog-controls");
      const search = create("input");
      search.type = "search";
      search.placeholder = words("Search models, notes, and trigger words", "搜索模型、备注和触发词");
      search.setAttribute("aria-label", search.placeholder);
      const filter = (label, options) => {
        const select = create("select");
        select.setAttribute("aria-label", label);
        for (const [key, text] of options) select.add(new Option(text, key));
        return select;
      };
      const choices = (key) => [...new Set(items.flatMap((row) =>
        Array.isArray(row[key]) ? row[key] : String(row[key] || "").split(/[/,，、|]/).map((part) => part.trim()).filter(Boolean)
      ))].sort();
      const match = (row, field, selected) => !selected || (Array.isArray(row[field])
        ? row[field].includes(selected) : String(row[field]).split(/[/,，、|]/).map((part) => part.trim()).includes(selected));
      const category = filter(words("Category", "分类"), [["", words("All categories", "所有分类")], ...choices("category").map((v) => [v, v])]);
      const model = filter(words("Base model", "支持模型"), [["", words("All base models", "所有支持模型")], ...choices("model_support").map((v) => [v, v])]);
      const pod = filter(words("Pod status", "Pod 状态"), [["", words("All Pod states", "所有 Pod 状态")], ["true", words("Loaded", "已加载")], ["false", words("Not loaded", "未加载")]]);
      const pageSize = filter(words("Rows per page", "每页条数"), [["25", "25"], ["50", "50"], ["100", "100"]]);
      pageSize.value = "50";
      controls.append(search, category, model, pod, pageSize);
      const status = create("p", "", "section-copy");
      status.setAttribute("aria-live", "polite");
      const table = create("table", "", "lora-catalog-table");
      const header = table.createTHead().insertRow();
      for (const text of [words("Preview", "预览"), words("Model", "模型"), words("Category", "分类"), words("Base model", "支持模型"), words("Pod", "Pod"), words("Effect", "效果")]) {
        const cell = create("th", text);
        cell.scope = "col";
        header.append(cell);
      }
      const tbody = table.createTBody();
      const wrapper = create("div", "", "lora-catalog-scroll");
      wrapper.append(table);
      const pager = create("div", "", "lora-catalog-pager");
      const previous = create("button", words("Previous", "上一页"), "ghost-button");
      const next = create("button", words("Next", "下一页"), "ghost-button");
      const pageLabel = create("span");
      pager.append(previous, pageLabel, next);
      const detail = create("dialog", "", "lora-catalog-dialog");
      detail.setAttribute("aria-label", words("Model details", "模型详情"));
      root.replaceChildren(controls, status, wrapper, pager, detail);
      let page = 1;

      function show(row) {
        const heading = create("div", "", "section-toolbar");
        const close = create("button", words("Close", "关闭"), "ghost-button");
        close.onclick = () => detail.close();
        heading.append(create("h3", value(row.lora_name)), close);
        const fields = create("dl");
        for (const [key, label] of [
          ["id", words("Note", "笔记")], ["lora_version", words("Version", "版本")], ["trigger_words", words("Trigger words", "触发词")],
          ["model_support", words("Base model", "支持模型")], ["effect", words("Effect", "效果")], ["notes", words("Notes", "备注")],
        ]) if (value(row[key])) fields.append(create("dt", label), create("dd", value(row[key])));
        detail.replaceChildren(heading, fields);
        attachPicture(detail, row, "preview", value(row.lora_name));
        detail.showModal();
      }

      function render() {
        const query = search.value.trim().toLowerCase();
        const filtered = items.filter((row) => match(row, "category", category.value)
          && match(row, "model_support", model.value)
          && (!pod.value || yes(row.pod_loaded) === (pod.value === "true"))
          && (!query || [row.title, row.lora_name, row.trigger_words, row.notes, row.effect].map(value).join(" ").toLowerCase().includes(query)));
        const size = Number(pageSize.value);
        const pages = Math.max(1, Math.ceil(filtered.length / size));
        page = Math.min(pages, Math.max(1, page));
        status.textContent = filtered.length ? words(`${filtered.length} of ${items.length} models`, `${filtered.length} / ${items.length} 个模型`)
          : items.length ? words("No models match the filters.", "没有符合条件的模型。") : words("No LoRA notes found in this folder.", "所选目录里没有 LoRA 笔记。");
        tbody.replaceChildren();
        for (const row of filtered.slice((page - 1) * size, page * size)) {
          const line = tbody.insertRow();
          const preview = line.insertCell();
          attachPicture(preview, row, "thumbnail", "");
          const open = create("button", value(row.lora_name), "ghost-button");
          open.onclick = () => show(row);
          line.insertCell().append(open);
          for (const item of [row.category, row.model_support, yes(row.pod_loaded) ? words("Loaded", "已加载") : "—", row.effect]) {
            line.insertCell().textContent = value(item) || "—";
          }
        }
        pageLabel.textContent = `${page} / ${pages}`;
        previous.disabled = page <= 1;
        next.disabled = page >= pages;
      }
      controls.addEventListener("input", () => { page = 1; render(); });
      previous.onclick = () => { page--; render(); };
      next.onclick = () => { page++; render(); };
      render();
    },
  };
})();
