const state = {
  restaurants: [], filtered: [], map: null, markers: [], activeMarkerId: null,
  hoveredMarkerId: null, labelFrame: null, nearbyCenter: null, nearbyName: "",
  nearbyRadius: 3000, centerMarker: null, nearbyCircle: null, autoComplete: null,
};
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

function distanceMeters(from, item) {
  const earthRadius = 6371000;
  const toRadians = (degrees) => degrees * Math.PI / 180;
  const latitudeDelta = toRadians(item.latitude - from.lat);
  const longitudeDelta = toRadians(item.longitude - from.lng);
  const latitude1 = toRadians(from.lat);
  const latitude2 = toRadians(item.latitude);
  const a = Math.sin(latitudeDelta / 2) ** 2 + Math.cos(latitude1) * Math.cos(latitude2) * Math.sin(longitudeDelta / 2) ** 2;
  return earthRadius * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

function formatDistance(meters) {
  return meters < 1000 ? `${Math.round(meters)} 米` : `${(meters / 1000).toFixed(1)} 公里`;
}

function applyFilters() {
  const query = $("#search").value.trim().toLowerCase();
  const district = $("#district").value;
  const cuisine = $("#cuisine").value;
  const price = $("#price").value;
  const rating = $("#rating").value;
  const year = $("#year").value;
  const filtered = state.restaurants.filter((item) => {
    const haystack = [item.name, item.branch, item.address, item.cuisine, item.review, ...(item.recommendedDishes || [])].join(" ").toLowerCase();
    return (!query || haystack.includes(query)) && (!district || item.district === district) && (!cuisine || item.cuisine === cuisine) && matchesPrice(item.pricePerPerson, price) && (!rating || (item.rating || "unknown") === rating) && (!year || (item.visitDate || "").startsWith(year));
  });
  state.filtered = state.nearbyCenter
    ? filtered
      .filter((item) => Number.isFinite(item.longitude) && Number.isFinite(item.latitude))
      .map((item) => ({ item, distance: distanceMeters(state.nearbyCenter, item) }))
      .filter((entry) => entry.distance <= state.nearbyRadius)
      .sort((a, b) => a.distance - b.distance)
      .map(({ item, distance }) => ({ ...item, __distance: distance }))
    : filtered;
  renderList();
  renderMarkers();
  $("#result-count").textContent = state.filtered.length;
}

function card(item) {
  const tags = [item.__distance != null ? `距中心 ${formatDistance(item.__distance)}` : "", item.district, item.cuisine, money(item.pricePerPerson), ratingLabels[item.rating || "unknown"]].filter(Boolean);
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
  state.activeMarkerId = id;
  updateMarkerLabels();
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
  state.map.on("zoomend", updateMarkerLabels);
  state.map.on("moveend", updateMarkerLabels);
  state.map.on("click", (event) => setNearbyCenter(event.lnglat, "地图选点"));
  initPlaceSearch();
  renderMarkers();
}

function locationValue(location) {
  if (!location) return null;
  const lng = typeof location.getLng === "function" ? location.getLng() : Number(location.lng);
  const lat = typeof location.getLat === "function" ? location.getLat() : Number(location.lat);
  return Number.isFinite(lng) && Number.isFinite(lat) ? { lng, lat } : null;
}

function initPlaceSearch() {
  AMap.plugin("AMap.AutoComplete", () => {
    state.autoComplete = new AMap.AutoComplete({ city: "武汉", citylimit: true, input: "place-search-input" });
    state.autoComplete.on("select", (event) => {
      const location = locationValue(event.poi && event.poi.location);
      if (location) setNearbyCenter(location, event.poi.name || "搜索地点");
      else searchPlace(event.poi && event.poi.name);
    });
  });
}

function searchPlace(keyword) {
  const query = String(keyword || "").trim();
  if (!query || !state.autoComplete) return;
  $("#nearby-status").textContent = `正在搜索“${query}”…`;
  state.autoComplete.search(query, (status, result) => {
    const tips = result && result.tips;
    const poi = status === "complete" && tips && tips.find((entry) => locationValue(entry.location));
    if (!poi) {
      if (result === "INVALID_USER_DOMAIN" || (result && result.info === "INVALID_USER_DOMAIN")) {
        $("#nearby-status").textContent = "当前网站域名未加入高德 Key 的域名白名单";
        return;
      }
      const serviceError = status === "error" || (result && result.info && result.info !== "OK");
      $("#nearby-status").textContent = serviceError
        ? "地点服务认证失败，请配置该 JS Key 对应的 AMAP_SECURITY_CODE"
        : `未在武汉找到“${query}”，请尝试更完整的地点名称`;
      return;
    }
    setNearbyCenter(locationValue(poi.location), poi.name || query);
  });
}

function renderNearbyCenter() {
  if (!state.map) return;
  if (state.centerMarker) state.map.remove(state.centerMarker);
  if (state.nearbyCircle) state.map.remove(state.nearbyCircle);
  state.centerMarker = null;
  state.nearbyCircle = null;
  if (!state.nearbyCenter) return;
  const position = [state.nearbyCenter.lng, state.nearbyCenter.lat];
  state.nearbyCircle = new AMap.Circle({
    map: state.map, center: position, radius: state.nearbyRadius,
    strokeColor: "#cf4f2f", strokeWeight: 2, strokeOpacity: .8,
    fillColor: "#cf4f2f", fillOpacity: .09, zIndex: 20,
  });
  state.centerMarker = new AMap.Marker({
    map: state.map, position, zIndex: 200,
    content: '<div class="nearby-center-marker"><span></span></div>',
    offset: new AMap.Pixel(-14, -14), title: state.nearbyName,
  });
}

function setNearbyCenter(location, name) {
  const center = locationValue(location);
  if (!center) return;
  state.nearbyCenter = center;
  state.nearbyName = name || "选定地点";
  state.nearbyRadius = Number($("#nearby-radius").value);
  $("#place-search-input").value = state.nearbyName === "地图选点" ? "" : state.nearbyName;
  $("#clear-nearby").hidden = false;
  applyFilters();
  renderNearbyCenter();
  const count = state.filtered.length;
  $("#nearby-status").textContent = `${state.nearbyName} · ${state.nearbyRadius / 1000} 公里内找到 ${count} 家餐厅`;
  if (!count) state.map.setZoomAndCenter(14, [center.lng, center.lat]);
}

function clearNearby() {
  state.nearbyCenter = null;
  state.nearbyName = "";
  $("#place-search-input").value = "";
  $("#clear-nearby").hidden = true;
  $("#nearby-status").textContent = "也可以直接点击地图选定中心点";
  renderNearbyCenter();
  applyFilters();
}

function markerLabelContent(item, opacity) {
  return `<span class="restaurant-marker-name" style="--label-opacity:${opacity}">${safe(item.name)}</span>`;
}

function updateMarkerLabels() {
  if (!state.map || !state.markers.length) return;
  if (state.labelFrame) cancelAnimationFrame(state.labelFrame);
  state.labelFrame = requestAnimationFrame(() => {
    const zoom = state.map.getZoom();
    const highlightedId = state.hoveredMarkerId || state.activeMarkerId;
    const settings = zoom >= 14
      ? { spacing: 0, opacity: 1 }
      : zoom >= 13
        ? { spacing: 78, opacity: .78 }
        : zoom >= 12
          ? { spacing: 112, opacity: .58 }
          : zoom >= 11
            ? { spacing: 148, opacity: .38 }
            : { spacing: Infinity, opacity: 0 };
    const occupied = [];
    const ordered = [...state.markers].sort((a, b) => {
      if (a.__restaurant.id === highlightedId) return -1;
      if (b.__restaurant.id === highlightedId) return 1;
      return (b.__restaurant.visitDate || "").localeCompare(a.__restaurant.visitDate || "");
    });

    ordered.forEach((marker) => {
      const item = marker.__restaurant;
      const highlighted = item.id === highlightedId;
      const pixel = state.map.lngLatToContainer(marker.getPosition());
      const point = { x: pixel.getX ? pixel.getX() : pixel.x, y: pixel.getY ? pixel.getY() : pixel.y };
      const collides = occupied.some((other) => Math.hypot(point.x - other.x, point.y - other.y) < settings.spacing);
      const visible = highlighted || (settings.opacity > 0 && !collides);
      const opacity = highlighted ? 1 : settings.opacity;
      const signature = visible ? `${item.name}:${opacity}` : "hidden";
      if (marker.__labelSignature !== signature) {
        marker.setLabel({ content: visible ? markerLabelContent(item, opacity) : "", direction: "top" });
        marker.__labelSignature = signature;
      }
      if (visible) occupied.push(point);
    });
  });
}

function renderMarkers() {
  if (!state.map || !window.AMap) return;
  if (state.markers.length) state.map.remove(state.markers);
  const valid = state.filtered.filter((item) => Number.isFinite(item.longitude) && Number.isFinite(item.latitude));
  state.markers = valid.map((item) => {
    const marker = new AMap.Marker({
      map: state.map,
      position: [item.longitude, item.latitude],
      title: item.name,
      label: { content: "", direction: "top" },
    });
    marker.__restaurant = item;
    marker.on("click", () => showDetails(item.id));
    marker.on("mouseover", () => { state.hoveredMarkerId = item.id; updateMarkerLabels(); });
    marker.on("mouseout", () => { state.hoveredMarkerId = null; updateMarkerLabels(); });
    return marker;
  });
  updateMarkerLabels();
  if (state.markers.length) {
    const fitTargets = state.nearbyCircle ? [...state.markers, state.nearbyCircle] : state.markers;
    state.map.setFitView(fitTargets, false, [120, 50, 50, 50], 15);
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
    $("#place-search-form").addEventListener("submit", (event) => { event.preventDefault(); searchPlace($("#place-search-input").value); });
    $("#nearby-radius").addEventListener("change", () => { state.nearbyRadius = Number($("#nearby-radius").value); if (state.nearbyCenter) setNearbyCenter(state.nearbyCenter, state.nearbyName); });
    $("#clear-nearby").addEventListener("click", clearNearby);
    $(".dialog-close").addEventListener("click", () => $("#details").close());
    $("#details").addEventListener("close", () => { state.activeMarkerId = null; updateMarkerLabels(); });
    $("#mobile-toggle").addEventListener("click", () => { document.body.classList.toggle("list-open"); $("#mobile-toggle").textContent = document.body.classList.contains("list-open") ? "查看地图" : "查看列表"; });
    applyFilters();
    if (await loadAmap()) initMap();
  } catch (error) {
    $("#status").innerHTML = `<div class="empty">${safe(error.message)}</div>`;
  }
}
main();
