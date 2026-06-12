const state = { restaurants: [], filtered: [], map: null, markers: [] };
const $ = (selector) => document.querySelector(selector);
const config = window.YUMMYMAP_CONFIG || {};

const ratingLabels = { recommended: "推荐", mixed: "有褒有贬", not_recommended: "不推荐", unknown: "待整理" };
const money = (value) => Number.isFinite(value) ? `¥${value}/人` : "人均未知";
const safe = (value = "") => String(value).replace(/[&<>'"]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[char]);

async function loadData() {
  const response = await fetch("./data/restaurants.json");
  if (!response.ok) throw new Error(`数据加载失败（${response.status}）`);
  const payload = await response.json();
  state.restaurants = Array.isArray(payload) ? payload : payload.restaurants || [];
}

function populateSelect(id, values) {
  const select = $(id);
  [...new Set(values.filter(Boolean))].sort((a, b) => a.localeCompare(b, "zh-CN")).forEach((value) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value;
    select.append(option);
  });
}

function matchesPrice(price, range) {
  if (!range) return true;
  if (!Number.isFinite(price)) return range === "unknown";
  if (range === "0-49") return price < 50;
  if (range === "50-99") return price >= 50 && price < 100;
  if (range === "100-199") return price >= 100 && price < 200;
  return price >= 200;
}

function applyFilters() {
  const query = $("#search").value.trim().toLowerCase();
  const district = $("#district").value;
  const cuisine = $("#cuisine").value;
  const price = $("#price").value;
  const rating = $("#rating").value;
  const year = $("#year").value;
  state.filtered = state.restaurants.filter((item) => {
    const haystack = [item.name, item.branch, item.address, item.cuisine, item.review, ...(item.recommendedDishes || [])].join(" ").toLowerCase();
    return (!query || haystack.includes(query)) && (!district || item.district === district) && (!cuisine || item.cuisine === cuisine) && matchesPrice(item.pricePerPerson, price) && (!rating || (item.rating || "unknown") === rating) && (!year || (item.visitDate || "").startsWith(year));
  });
  renderList();
  renderMarkers();
  $("#result-count").textContent = state.filtered.length;
}

function card(item) {
  const tags = [item.district, item.cuisine, money(item.pricePerPerson), ratingLabels[item.rating || "unknown"]].filter(Boolean);
  return `<button class="restaurant-card" type="button" data-id="${safe(item.id)}"><h2>${safe(item.name)}${item.branch ? `（${safe(item.branch)}）` : ""}</h2><div class="tags">${tags.map((tag) => `<span class="tag">${safe(tag)}</span>`).join("")}</div><p>${safe(item.address || "地址待复核")}</p><p>${safe(item.review || "评价待整理")}</p></button>`;
}

function renderList() {
  const list = $("#restaurant-list");
  const status = $("#status");
  list.innerHTML = state.filtered.map(card).join("");
  status.innerHTML = state.restaurants.length ? "" : `<div class="empty"><strong>地图框架已经就绪，餐厅数据正在整理。</strong><br>运行 <code>python scripts/collect_bilibili.py</code> 获取视频清单，再在 <code>data/review_queue.csv</code> 中复核餐厅信息。</div>`;
  list.querySelectorAll("[data-id]").forEach((button) => button.addEventListener("click", () => showDetails(button.dataset.id)));
}

function showDetails(id) {
  const item = state.restaurants.find((entry) => entry.id === id);
  if (!item) return;
  const dishes = (item.recommendedDishes || []).join("、") || "待整理";
  $("#details-content").innerHTML = `<h2>${safe(item.name)}${item.branch ? `（${safe(item.branch)}）` : ""}</h2><div class="tags"><span class="tag">${safe(ratingLabels[item.rating || "unknown"])}</span><span class="tag">${safe(money(item.pricePerPerson))}</span></div><p>${safe(item.review || "评价待整理")}</p><dl class="detail-grid"><dt>地址</dt><dd>${safe(item.address || "待复核")}</dd><dt>区域 / 菜系</dt><dd>${safe([item.district, item.cuisine].filter(Boolean).join(" · ") || "待整理")}</dd><dt>推荐菜</dt><dd>${safe(dishes)}</dd><dt>探店日期</dt><dd>${safe(item.visitDate || "未知")}</dd><dt>数据状态</dt><dd>${safe(item.verificationStatus || "待复核")}</dd></dl>${item.videoUrl ? `<a class="video-link" href="${safe(item.videoUrl)}" target="_blank" rel="noreferrer">观看原视频</a>` : ""}`;
  $("#details").showModal();
}

function loadAmap() {
  if (!config.amapKey) {
    $("#map-message").hidden = false;
    $("#map-message").innerHTML = "尚未配置高德地图密钥。餐厅列表仍可使用；部署时请在 GitHub Actions Secrets 中设置 <code>AMAP_JS_KEY</code> 和 <code>AMAP_SECURITY_CODE</code>。";
    return Promise.resolve(false);
  }
  window._AMapSecurityConfig = { securityJsCode: config.amapSecurityCode || "" };
  return new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = `https://webapi.amap.com/maps?v=2.0&key=${encodeURIComponent(config.amapKey)}`;
    script.onload = () => resolve(true);
    script.onerror = () => reject(new Error("高德地图加载失败"));
    document.head.append(script);
  });
}

function initMap() {
  state.map = new AMap.Map("map", { zoom: 11, center: [114.3055, 30.5928], viewMode: "2D" });
  renderMarkers();
}

function renderMarkers() {
  if (!state.map || !window.AMap) return;
  state.map.clearMap();
  const valid = state.filtered.filter((item) => Number.isFinite(item.longitude) && Number.isFinite(item.latitude));
  state.markers = valid.map((item) => {
    const marker = new AMap.Marker({
      map: state.map,
      position: [item.longitude, item.latitude],
      title: item.name,
      label: { content: item.name, direction: "top" },
    });
    marker.on("click", () => showDetails(item.id));
    return marker;
  });
  if (state.markers.length) {
    state.map.setFitView(state.markers, false, [50, 50, 50, 50], 15);
  }
}

async function main() {
  try {
    await loadData();
    populateSelect("#district", state.restaurants.map((item) => item.district));
    populateSelect("#cuisine", state.restaurants.map((item) => item.cuisine));
    populateSelect("#year", state.restaurants.map((item) => (item.visitDate || "").slice(0, 4)));
    ["#search", "#district", "#cuisine", "#price", "#rating", "#year"].forEach((id) => $(id).addEventListener(id === "#search" ? "input" : "change", applyFilters));
    $("#reset").addEventListener("click", () => { $("#search").value = ""; ["#district", "#cuisine", "#price", "#rating", "#year"].forEach((id) => $(id).value = ""); applyFilters(); });
    $(".dialog-close").addEventListener("click", () => $("#details").close());
    $("#mobile-toggle").addEventListener("click", () => { document.body.classList.toggle("list-open"); $("#mobile-toggle").textContent = document.body.classList.contains("list-open") ? "查看地图" : "查看列表"; });
    applyFilters();
    if (await loadAmap()) initMap();
  } catch (error) {
    $("#status").innerHTML = `<div class="empty">${safe(error.message)}</div>`;
  }
}
main();
