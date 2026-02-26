(function () {
  function parseEvents() {
    const node = document.getElementById("event-timestamps");
    if (!node) return [];
    try {
      const raw = JSON.parse(node.textContent || "[]");
      return Array.isArray(raw)
        ? raw
            .map((ts) => new Date(ts))
            .filter((d) => !Number.isNaN(d.getTime()))
        : [];
    } catch (_err) {
      return [];
    }
  }

  function setTimezoneLabel() {
    const zone = Intl.DateTimeFormat().resolvedOptions().timeZone || "Unknown";
    const el = document.getElementById("browser-timezone");
    if (el) el.textContent = zone;
  }

  function empty(elId, text) {
    const el = document.getElementById(elId);
    if (!el) return;
    el.innerHTML = '<p class="viz-placeholder">' + text + "</p>";
  }

  function renderPolarHourChart(events) {
    if (!events.length) return empty("polar-chart", "No call events yet.");
    const el = document.getElementById("polar-chart");
    if (!el) return;

    const counts = new Array(24).fill(0);
    events.forEach((d) => counts[d.getHours()]++);
    const maxCount = Math.max(...counts, 1);

    const size = 260;
    const c = size / 2;
    const inner = 24;
    const outer = 92;
    const angleStep = (Math.PI * 2) / 24;

    const bars = counts
      .map((count, h) => {
        const radius = inner + (count / maxCount) * (outer - inner);
        const angle = (h - 6) * angleStep; // rotate so midnight starts at top
        const x2 = c + Math.cos(angle) * radius;
        const y2 = c + Math.sin(angle) * radius;
        const opacity = count ? 0.25 + (count / maxCount) * 0.75 : 0.12;
        return (
          '<line x1="' +
          c +
          '" y1="' +
          c +
          '" x2="' +
          x2.toFixed(1) +
          '" y2="' +
          y2.toFixed(1) +
          '" stroke="#f59e0b" stroke-width="7" stroke-linecap="round" stroke-opacity="' +
          opacity.toFixed(2) +
          '"/>'
        );
      })
      .join("");

    const labels = [0, 6, 12, 18]
      .map((h) => {
        const angle = (h - 6) * angleStep;
        const r = outer + 18;
        const x = c + Math.cos(angle) * r;
        const y = c + Math.sin(angle) * r + 3;
        const txt = h === 0 ? "12a" : h === 12 ? "12p" : h + "";
        return (
          '<text x="' +
          x.toFixed(1) +
          '" y="' +
          y.toFixed(1) +
          '" font-size="10" fill="#94a3b8" text-anchor="middle">' +
          txt +
          "</text>"
        );
      })
      .join("");

    el.innerHTML =
      '<svg width="' +
      size +
      '" height="' +
      size +
      '" viewBox="0 0 ' +
      size +
      " " +
      size +
      '" xmlns="http://www.w3.org/2000/svg">' +
      '<circle cx="' +
      c +
      '" cy="' +
      c +
      '" r="' +
      outer +
      '" fill="none" stroke="#334155" stroke-width="1"/>' +
      bars +
      labels +
      '<text x="' +
      c +
      '" y="' +
      (c + 4) +
      '" font-size="11" fill="#e5e7eb" text-anchor="middle">Local Hours</text>' +
      "</svg>";
  }

  function localDateKey(d) {
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    return y + "-" + m + "-" + day;
  }

  function renderRolling60(events) {
    if (!events.length) return empty("daily60-chart", "No call events yet.");
    const el = document.getElementById("daily60-chart");
    if (!el) return;

    const byDay = new Map();
    events.forEach((d) => {
      const key = localDateKey(d);
      byDay.set(key, (byDay.get(key) || 0) + 1);
    });

    const days = [];
    const now = new Date();
    for (let i = 59; i >= 0; i--) {
      const d = new Date(now);
      d.setHours(0, 0, 0, 0);
      d.setDate(d.getDate() - i);
      const key = localDateKey(d);
      days.push({ key, count: byDay.get(key) || 0 });
    }

    const maxCount = Math.max(...days.map((d) => d.count), 1);
    const width = 760;
    const height = 220;
    const left = 34;
    const right = 12;
    const top = 18;
    const bottom = 26;
    const plotW = width - left - right;
    const plotH = height - top - bottom;
    const bw = plotW / days.length;

    const bars = days
      .map((d, i) => {
        const h = (d.count / maxCount) * plotH;
        const x = left + i * bw;
        const y = top + (plotH - h);
        return (
          '<rect x="' +
          x.toFixed(2) +
          '" y="' +
          y.toFixed(2) +
          '" width="' +
          Math.max(bw - 1.5, 1).toFixed(2) +
          '" height="' +
          h.toFixed(2) +
          '" fill="#f59e0b" rx="2"/>'
        );
      })
      .join("");

    el.innerHTML =
      '<svg width="100%" height="220" viewBox="0 0 ' +
      width +
      " " +
      height +
      '" xmlns="http://www.w3.org/2000/svg">' +
      '<line x1="' +
      left +
      '" y1="' +
      (top + plotH) +
      '" x2="' +
      (width - right) +
      '" y2="' +
      (top + plotH) +
      '" stroke="#334155"/>' +
      bars +
      '<text x="' +
      left +
      '" y="' +
      (height - 8) +
      '" font-size="10" fill="#94a3b8">60d ago</text>' +
      '<text x="' +
      (width - right - 2) +
      '" y="' +
      (height - 8) +
      '" font-size="10" fill="#94a3b8" text-anchor="end">Today</text>' +
      "</svg>";
  }

  function renderWeekdayChart(events) {
    if (!events.length) return empty("weekday-chart", "No call events yet.");
    const el = document.getElementById("weekday-chart");
    if (!el) return;

    const dayName = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
    const byDate = new Map();
    events.forEach((d) => {
      const key = localDateKey(d);
      byDate.set(key, (byDate.get(key) || 0) + 1);
    });

    const perWeekday = Array.from({ length: 7 }, () => []);
    byDate.forEach((count, key) => {
      const d = new Date(key + "T00:00:00");
      perWeekday[d.getDay()].push(count);
    });

    const avg = perWeekday.map((arr) =>
      arr.length ? arr.reduce((a, b) => a + b, 0) / arr.length : 0
    );
    const overall =
      avg.reduce((a, b) => a + b, 0) / (avg.filter((n) => n > 0).length || 1);
    const maxAvg = Math.max(...avg, 1);

    const rows = avg
      .map((v, i) => {
        const pct = (v / maxAvg) * 100;
        const delta = v - overall;
        const deltaLabel =
          (delta >= 0 ? "+" : "") +
          delta.toFixed(2) +
          " vs avg";
        const color = delta >= 0 ? "#22c55e" : "#f97316";
        return (
          '<div style="display:grid;grid-template-columns:44px 1fr 76px;gap:10px;align-items:center;margin:6px 0;">' +
          '<div style="color:#cbd5e1;font-size:12px;">' +
          dayName[i] +
          "</div>" +
          '<div style="height:14px;background:#1f2937;border:1px solid #334155;border-radius:7px;overflow:hidden;">' +
          '<div style="height:100%;width:' +
          pct.toFixed(1) +
          '%;background:#f59e0b;"></div></div>' +
          '<div style="font-size:11px;color:' +
          color +
          ';text-align:right;">' +
          deltaLabel +
          "</div>" +
          "</div>"
        );
      })
      .join("");

    el.innerHTML = rows;
  }

  function main() {
    setTimezoneLabel();
    const events = parseEvents();
    renderPolarHourChart(events);
    renderRolling60(events);
    renderWeekdayChart(events);
  }

  main();
})();
