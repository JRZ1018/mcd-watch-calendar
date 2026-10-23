"use strict";
const $ = (selector) => document.querySelector(selector);
const today = new Intl.DateTimeFormat("sv-SE", {timeZone:"Asia/Shanghai"}).format(new Date());
const [year, month, day] = today.split("-");
$("#today-day").textContent = day;
$("#today-month").textContent = `${year} 年 ${Number(month)} 月 / 北京时间`;
const feedOptions = {
  "": {path:"calendar.ics", label:"全部活动"},
  "早餐": {path:"feeds/breakfast.ics", label:"早餐"},
  "麦咖啡": {path:"feeds/coffee.ics", label:"咖啡"},
  "联名": {path:"feeds/collabs.ics", label:"联名周边"}
};
let activeFeed = new URL("calendar.ics", window.location.href).href;
function setSubscription(topic) {
  const option = feedOptions[topic];
  activeFeed = new URL(option.path, window.location.href).href;
  $("#subscribe").href = activeFeed.replace(/^https?:/, "webcal:");
  document.querySelector(".download").href = activeFeed;
  $("#subscribe").firstChild.textContent = topic ? `订阅${option.label} ` : "订阅日历 ";
  $("#feed-note").textContent = `当前订阅范围：${option.label}。主题切换会同时切换订阅源；搜索和日期开关仅影响下方列表。`;
  $("#copy-status").textContent = "";
}
$("#subscribe").href = activeFeed.replace(/^https?:/, "webcal:");
$("#copy-feed").addEventListener("click", async () => {
  try { await navigator.clipboard.writeText(activeFeed); $("#copy-status").textContent = "已复制 HTTPS 订阅地址，在日历客户端中粘贴即可。"; }
  catch { $("#copy-status").textContent = `订阅地址：${activeFeed}`; }
});
let allEvents = [], keyword = "";
function render() {
  const query = $("#search").value.trim().toLocaleLowerCase();
  const future = $("#future-only").checked;
  const selected = allEvents.filter(event => {
    const haystack = `${event.title}\n${event.source_text}`.toLocaleLowerCase();
    return (!future || event.end >= today) && (!keyword || haystack.includes(keyword)) && (!query || haystack.includes(query));
  });
  const list = $("#activity-list"); list.replaceChildren();
  if (!selected.length) { const empty = document.createElement("p"); empty.className = "empty"; empty.textContent = "当前筛选没有匹配条目，可尝试其他关键词或查看往期展示日期。"; list.append(empty); return; }
  const grouped = new Map();
  for (const event of selected) { if (!grouped.has(event.start)) grouped.set(event.start, []); grouped.get(event.start).push(event); }
  for (const [date, events] of grouped) {
    const section = document.createElement("section"); section.className = "day-group";
    const heading = document.createElement("h3"); heading.className = "day-heading";
    const dateNumber = document.createElement("b"); dateNumber.textContent = date.slice(5).replace("-", "/");
    const meta = document.createElement("span"); meta.textContent = date === today ? "今天 · 展示日" : `${date.slice(0,4)} · 展示日`;
    heading.append(dateNumber, meta); section.append(heading);
    const items = document.createElement("div");
    for (const event of events) {
      const item = document.createElement("details"); item.className = "event";
      const summary = document.createElement("summary"), title = document.createElement("h3");
      title.textContent = event.title.replace(/｜活动日历条目$/, ""); summary.append(title);
      const label = document.createElement("small"); label.textContent = "官方 MCP 活动日历 · 展开查看原文与参与条件";
      const text = document.createElement("pre"); text.textContent = event.source_text;
      item.append(summary, label, text); items.append(item);
    }
    section.append(items); list.append(section);
  }
}
document.querySelectorAll("[data-keyword]").forEach(button => button.addEventListener("click", () => {
  keyword = button.dataset.keyword;
  setSubscription(keyword);
  document.querySelectorAll("[data-keyword]").forEach(other => other.setAttribute("aria-pressed", String(other === button)));
  render();
}));
$("#search").addEventListener("input", render); $("#future-only").addEventListener("change", render);
(async () => {
  try {
    const responses = await Promise.all([fetch("events.json", {cache:"no-cache"}), fetch("status.json", {cache:"no-cache"})]);
    if (responses.some(response => !response.ok)) throw new Error("Calendar unavailable");
    const [document, status] = await Promise.all(responses.map(response => response.json()));
    if (document.mode !== "live" || !Array.isArray(document.events)) throw new Error("Invalid calendar");
    allEvents = document.events.slice().sort((a,b) => a.start.localeCompare(b.start) || a.id.localeCompare(b.id));
    $("#event-count").textContent = allEvents.length; $("#day-count").textContent = new Set(allEvents.map(event => event.start)).size;
    const fetched = new Date(status.retrieved_at);
    const stamp = new Intl.DateTimeFormat("zh-CN", {timeZone:"Asia/Shanghai",month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit",hour12:false}).format(fetched);
    $("#updated").textContent = `最近成功查询 ${stamp}（北京时间）` + (Date.now() - fetched.getTime() > 36*3600000 ? " · 数据可能已过期，请以官方实时信息为准。" : " · 定期更新");
    render();
  } catch {
    $("#updated").textContent = "暂时无法读取最近一次活动数据";
    $("#activity-list").replaceChildren(); const error = document.createElement("p"); error.className = "empty"; error.textContent = "日历数据暂时不可用，请稍后刷新或到项目仓库查看最后成功的文件。"; $("#activity-list").append(error);
  }
})();
