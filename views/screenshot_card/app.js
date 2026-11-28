// 截图结果卡片：展示来源链接和缩略图；原图通过图片附件交付。
const bridge = window.AstrBotPluginView || window.AstrBotPluginPage;
const card = document.getElementById("card");

function render(data) {
  const items = Array.isArray(data?.items) ? data.items : [];
  card.innerHTML = "";
  if (!items.length) {
    card.innerHTML = '<p class="note">没有截图结果。</p>';
    return;
  }
  items.forEach((item) => {
    const row = document.createElement("div");
    row.setAttribute("role", "listitem");
    if (item.error) {
      row.className = "error";
      const label = document.createElement("span");
      label.className = "error-label";
      label.textContent = "失败";
      row.appendChild(label);
      row.appendChild(document.createTextNode(`${item.url}\n${item.error}`));
    } else {
      row.className = "item";
      const thumbCell = document.createElement("div");
      if (item.thumb) {
        const img = document.createElement("img");
        img.className = "thumb";
        img.src = item.thumb;
        img.alt = "";
        img.loading = "lazy";
        thumbCell.appendChild(img);
      } else {
        const missing = document.createElement("div");
        missing.className = "thumb-missing";
        missing.textContent = "无预览";
        thumbCell.appendChild(missing);
      }
      const meta = document.createElement("div");
      meta.className = "meta";
      const title = document.createElement("div");
      title.className = "title";
      title.textContent = item.title || item.url;
      meta.appendChild(title);
      const link = document.createElement("a");
      link.className = "link";
      link.href = item.final_url || item.url;
      link.target = "_blank";
      link.rel = "noreferrer noopener";
      link.textContent = item.final_url || item.url;
      meta.appendChild(link);
      row.append(thumbCell, meta);
    }
    card.appendChild(row);
  });
}

async function init() {
  try {
    await bridge.ready();
    bridge.view.subscribe(({ data }) => render(data));
  } catch (e) {
    card.innerHTML = `<p class="note">${e.message}</p>`;
  }
}

init();
