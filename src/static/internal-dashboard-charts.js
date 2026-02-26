(function () {
  function parseEvents() {
    const node = document.getElementById("event-timestamps");
    if (!node) return [];
    try {
      const raw = JSON.parse(node.textContent || "[]");
      return Array.isArray(raw)
        ? raw
            .map((evt) => ({
              timestamp: evt && evt.timestamp ? evt.timestamp : null,
              fromNumber: evt && evt.fromNumber ? evt.fromNumber : "unknown",
            }))
            .map((evt) => ({
              ...evt,
              date: new Date(evt.timestamp),
            }))
            .filter((evt) => !Number.isNaN(evt.date.getTime()))
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

  function clamp(v, min, max) {
    return Math.max(min, Math.min(max, v));
  }

  function rgba(arr, alphaOverride) {
    if (!Array.isArray(arr) || arr.length < 4) return "rgba(255,255,255,1)";
    const a = alphaOverride !== undefined ? alphaOverride : arr[3] / 255;
    return "rgba(" + arr[0] + "," + arr[1] + "," + arr[2] + "," + a + ")";
  }

  function lerp(a, b, t) {
    return a + (b - a) * t;
  }

  function fetchDoorConfig() {
    return fetch("/art/door-visualization-config.json", { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .catch(() => null);
  }

  function loadImageDimensions(src) {
    return new Promise((resolve) => {
      const img = new Image();
      img.onload = function () {
        resolve({
          width: img.naturalWidth || 900,
          height: img.naturalHeight || 900,
        });
      };
      img.onerror = function () {
        resolve({ width: 900, height: 900 });
      };
      img.src = src;
    });
  }

  function renderPolarHourChart(events) {
    if (!events.length) return empty("polar-chart", "No call events yet.");
    const el = document.getElementById("polar-chart");
    if (!el) return;

    const counts = new Array(24).fill(0);
    events.forEach((evt) => counts[evt.date.getHours()]++);
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
    events.forEach((evt) => {
      const key = localDateKey(evt.date);
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

    const yTicks = [];
    for (let i = 0; i <= 4; i++) {
      const ratio = i / 4;
      const y = top + (plotH - ratio * plotH);
      const val = Math.round(ratio * maxCount);
      yTicks.push(
        '<line x1="' +
          left +
          '" y1="' +
          y.toFixed(1) +
          '" x2="' +
          (width - right) +
          '" y2="' +
          y.toFixed(1) +
          '" stroke="#334155" stroke-opacity="0.45"/>'
      );
      yTicks.push(
        '<text x="' +
          (left - 6) +
          '" y="' +
          (y + 3).toFixed(1) +
          '" font-size="10" fill="#94a3b8" text-anchor="end">' +
          val +
          "</text>"
      );
    }

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
      yTicks.join("") +
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
    events.forEach((evt) => {
      const key = localDateKey(evt.date);
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

  function renderDoorHistogram(events, cfg) {
    const el = document.getElementById("weekday-chart");
    if (!el) return;
    if (!cfg || !Array.isArray(cfg.doors)) {
      return empty("weekday-chart", "Door config missing.");
    }

    const byNumber = new Map();
    events.forEach((evt) => {
      byNumber.set(evt.fromNumber, (byNumber.get(evt.fromNumber) || 0) + 1);
    });

    const rows = cfg.doors
      .map((d) => {
        const raw = byNumber.get(d.fromNumber) || 0;
        const count = Math.min(raw, 100);
        const pct = (count / 100) * 100;
        return (
          '<div style="display:grid;grid-template-columns:58px 1fr 70px;gap:10px;align-items:center;margin:8px 0;">' +
          '<div style="color:#cbd5e1;font-size:12px;">' +
          d.name +
          "</div>" +
          '<div style="height:14px;background:#1f2937;border:1px solid #334155;border-radius:7px;overflow:hidden;">' +
          '<div style="height:100%;width:' +
          pct.toFixed(1) +
          '%;background:#f59e0b;"></div></div>' +
          '<div style="font-size:11px;color:#94a3b8;text-align:right;">' +
          raw +
          (raw > 100 ? " (cap 100)" : "") +
          "</div>" +
          "</div>"
        );
      })
      .join("");
    el.innerHTML = rows;
  }

  function renderDoorRipples(events, cfg, imageSize) {
    const mapWrap = document.getElementById("door-ripple-map");
    if (!mapWrap) return;
    if (!cfg || !Array.isArray(cfg.doors)) {
      mapWrap.innerHTML = '<p class="viz-placeholder">Door config missing.</p>';
      return;
    }

    const totalDays = Math.max(1, Number(cfg.totalDays || 60));
    const startSize = Number(cfg.startSizeInPixels || 28);
    const endSize = Number(cfg.endSizeInPixels || 210);
    const thickness = Math.max(1, Number(cfg.circleThicknessInPixels || 2));
    const startColor = cfg.startColorRGBA || [245, 158, 11, 255];
    const endColor = cfg.endColorRGBA || [59, 130, 246, 20];

    const now = Date.now();
    const msPerDay = 24 * 60 * 60 * 1000;
    const thirtyMinMs = 30 * 60 * 1000;

    const doorByNumber = new Map(cfg.doors.map((d) => [d.fromNumber, d]));

    const ripples = [];
    const flashRings = [];

    events.forEach((evt) => {
      const door = doorByNumber.get(evt.fromNumber);
      if (!door) return;
      const ageMs = now - evt.date.getTime();
      if (ageMs < 0) return;
      if (ageMs <= thirtyMinMs) {
        flashRings.push({ door, ageMs });
        return;
      }

      let ageDays = ageMs / msPerDay;
      ageDays = clamp(ageDays, 1, totalDays);
      if (ageDays > totalDays) return;
      const t = (ageDays - 1) / (totalDays - 1 || 1);
      const radius = lerp(startSize, endSize, t);
      const alpha = lerp(startColor[3] / 255, endColor[3] / 255, t);
      const color = rgba(
        [
          Math.round(lerp(startColor[0], endColor[0], t)),
          Math.round(lerp(startColor[1], endColor[1], t)),
          Math.round(lerp(startColor[2], endColor[2], t)),
          255,
        ],
        alpha
      );

      ripples.push({
        cx: door.x,
        cy: door.y,
        r: radius,
        stroke: color,
      });
    });

    const w = imageSize && imageSize.width ? imageSize.width : 900;
    const h = imageSize && imageSize.height ? imageSize.height : 900;
    const circles = ripples
      .map(
        (r) =>
          '<circle cx="' +
          r.cx +
          '" cy="' +
          r.cy +
          '" r="' +
          r.r.toFixed(1) +
          '" fill="none" stroke="' +
          r.stroke +
          '" stroke-width="' +
          thickness.toFixed(1) +
          '"/>'
      )
      .join("");

    const doorMarkers = cfg.doors
      .map(
        (d, i) =>
          '<text x="' +
          d.x +
          '" y="' +
          d.y +
          '" font-size="50" fill="#000000" stroke="#ffffff" stroke-width="4" paint-order="stroke fill" text-anchor="middle" dominant-baseline="middle">' +
          (i + 1) +
          "</text>"
      )
      .join("");

    const flashAnim = flashRings
      .map((f, i) => {
        const proximity = 1 - clamp(f.ageMs / thirtyMinMs, 0, 1);
        const dur = lerp(1.4, 0.18, proximity); // more recent => faster
        return (
          '<circle cx="' +
          f.door.x +
          '" cy="' +
          f.door.y +
          '" r="' +
          startSize.toFixed(1) +
          '" fill="none" stroke="#ff0000" stroke-width="' +
          thickness.toFixed(1) +
          '">' +
          '<animate attributeName="stroke" values="#ff0000ff;#ffffffff;#ff0000ff" dur="' +
          dur.toFixed(2) +
          's" repeatCount="indefinite" />' +
          '<animate attributeName="opacity" values="1;0.45;1" dur="' +
          dur.toFixed(2) +
          's" repeatCount="indefinite" />' +
          "</circle>"
        );
      })
      .join("");

    mapWrap.innerHTML =
      '<svg width="100%" viewBox="0 0 ' +
      w +
      " " +
      h +
      '" xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="xMidYMid meet">' +
      '<image href="/art/ablon.png" x="0" y="0" width="' +
      w +
      '" height="' +
      h +
      '"/>' +
      circles +
      flashAnim +
      doorMarkers +
      "</svg>";
  }

  function main() {
    setTimezoneLabel();
    const events = parseEvents();
    renderPolarHourChart(events);
    renderRolling60(events);
    renderWeekdayChart(events);
    fetchDoorConfig().then((cfg) => {
      renderDoorHistogram(events, cfg);
      loadImageDimensions("/art/ablon.png").then((size) => {
        renderDoorRipples(events, cfg, size);
      });
    });
  }

  main();
})();
