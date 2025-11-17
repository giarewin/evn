// evn_chart.js

// Đăng ký plugin hiển thị số trên cột
if (typeof ChartDataLabels !== "undefined") {
  Chart.register(ChartDataLabels);
}

// Đăng ký plugin zoom (UMD trên window)
(function registerZoomPlugin() {
  if (!Chart || !Chart.registry) return;
  try {
    const already = Chart.registry.plugins.get("zoom");
    if (already) return;
  } catch (e) {}

  const w = typeof window !== "undefined" ? window : {};
  if (w.ChartZoom) {
    Chart.register(w.ChartZoom);
  } else if (w.zoomPlugin) {
    Chart.register(w.zoomPlugin);
  }
})();

const REFRESH_MS = 5000;

let AVAILABLE_YEARS = [];
const YEAR_SCAN_BACK = 5;
const YEAR_SCAN_AHEAD = 1;

let chart = null;
let currentDate = null;  // YYYY-MM-DD
let currentMonth = null; // YYYY-MM
let currentYear = null;  // YYYY
let currentMode = "year";

const STORAGE_KEY = "evnChartSettings";

function loadSettings() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return {};
    return JSON.parse(raw);
  } catch (e) {
    return {};
  }
}

function saveSettings() {
  const data = {
    mode: currentMode,
    date: currentDate,
    month: currentMonth,
    year: currentYear,
  };
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
  } catch (e) {}
}

function isValidMode(m) {
  return m === "day" || m === "month" || m === "year" || m === "yearsum";
}

// CSV trong thư mục ./data cạnh file HTML
function getCsvUrlFromYear(yearStr) {
  const y = String(yearStr || "").slice(0, 4);
  const yNum = parseInt(y, 10);
  if (Number.isNaN(yNum)) {
    const today = new Date();
    return `data/${today.getFullYear()}.csv`;
  }
  return `data/${yNum}.csv`;
}

async function detectAvailableYears() {
  const today = new Date();
  const thisYear = today.getFullYear();
  const startYear = thisYear - YEAR_SCAN_BACK;
  const endYear = thisYear + YEAR_SCAN_AHEAD;

  const found = [];
  for (let y = startYear; y <= endYear; y++) {
    try {
      const res = await fetch(`data/${y}.csv?check=${Date.now()}`);
      if (res.ok) found.push(y);
    } catch (e) {}
  }

  if (found.length === 0) found.push(thisYear);
  AVAILABLE_YEARS = found.sort((a, b) => a - b);
}

function formatDateDisplay(ymd) {
  const parts = (ymd || "").split("-");
  if (parts.length !== 3) return "--/--/----";
  const [y, m, d] = parts;
  return `${d}-${m}-${y}`;
}

function formatMonthDisplay(ym) {
  const parts = (ym || "").split("-");
  if (parts.length !== 2) return "--/----";
  const [y, m] = parts;
  return `${m}-${y}`;
}

function updateDateDisplay(dateStr) {
  const txt = formatDateDisplay(dateStr);
  document.getElementById("dateDisplay").textContent = txt;
  document.getElementById("dateFooter").textContent = txt;
}

function updateMonthDisplay(monthStr) {
  const txt = formatMonthDisplay(monthStr);
  document.getElementById("monthDisplay").textContent = txt;
  document.getElementById("dateFooter").textContent = txt;
}

function updateYearDisplay(yearStr) {
  const txt = yearStr || "----";
  document.getElementById("yearDisplay").textContent = txt;
  document.getElementById("dateFooter").textContent = txt;
}

function updateYearSumFooter() {
  document.getElementById("dateFooter").textContent = "Các năm";
}

function getDaysInMonth(ym) {
  const parts = (ym || "").split("-");
  if (parts.length !== 2) return 31;
  const year = parseInt(parts[0], 10);
  const month = parseInt(parts[1], 10);
  if (Number.isNaN(year) || Number.isNaN(month)) return 31;
  return new Date(year, month, 0).getDate();
}

function populateYearOptions() {
  const select = document.getElementById("yearPicker");
  select.innerHTML = "";
  AVAILABLE_YEARS.forEach((y) => {
    const opt = document.createElement("option");
    opt.value = String(y);
    opt.textContent = String(y);
    select.appendChild(opt);
  });
}

function ensureDefaultDate(savedDate) {
  const input = document.getElementById("datePicker");
  if (savedDate) input.value = savedDate;

  if (!input.value) {
    const today = new Date();
    const yyyy = today.getFullYear();
    const mm = String(today.getMonth() + 1).padStart(2, "0");
    const dd = String(today.getDate()).padStart(2, "0");
    input.value = `${yyyy}-${mm}-${dd}`;
  }
  currentDate = input.value;
}

function ensureDefaultMonth(savedMonth) {
  const input = document.getElementById("monthPicker");
  if (savedMonth) input.value = savedMonth;

  if (!input.value) {
    const today = new Date();
    const yyyy = today.getFullYear();
    const mm = String(today.getMonth() + 1).padStart(2, "0");
    input.value = `${yyyy}-${mm}`;
  }
  currentMonth = input.value;
}

function ensureDefaultYear(savedYear) {
  const select = document.getElementById("yearPicker");
  const today = new Date();
  const thisYear = today.getFullYear();

  let targetYear = null;

  if (savedYear && AVAILABLE_YEARS.includes(Number(savedYear))) {
    targetYear = Number(savedYear);
  } else if (AVAILABLE_YEARS.includes(thisYear)) {
    targetYear = thisYear;
  } else if (AVAILABLE_YEARS.length > 0) {
    targetYear = AVAILABLE_YEARS[AVAILABLE_YEARS.length - 1];
  } else {
    targetYear = thisYear;
  }

  select.value = String(targetYear);
  currentYear = select.value;
}

/* Mua = vàng, Bán = xanh lá */
function makeBuyColors(buyData) {
  return buyData.map((v) =>
    v > 0 ? "rgba(250, 204, 21, 0.85)" : "rgba(209, 213, 219, 0.8)"
  );
}

function makeSellColors(sellData) {
  return sellData.map((v) =>
    v > 0 ? "rgba(34, 197, 94, 0.85)" : "rgba(209, 213, 219, 0.8)"
  );
}

// ===== Helpers định dạng số theo mode =====
function formatKwhValue(v) {
  if (!v || v <= 0) return "";
  if (currentMode === "day") return v.toFixed(2);
  if (currentMode === "month") return v.toFixed(1);
  return String(Math.round(v));
}

function formatMoneyValue(v) {
  if (!v || v <= 0) return "";
  if (currentMode === "day") return v.toFixed(2) + "K";
  if (currentMode === "month") return v.toFixed(1) + "K";
  return String(Math.round(v)) + "K";
}

function formatTooltipKwh(v) {
  if (!v || v <= 0) return "0";
  if (currentMode === "day") return v.toFixed(2);
  if (currentMode === "month") return v.toFixed(1);
  return String(Math.round(v));
}

function formatTooltipMoney(v) {
  if (!v || v <= 0) return "0";
  if (currentMode === "day") return v.toFixed(2);
  if (currentMode === "month") return v.toFixed(1);
  return String(Math.round(v));
}

// ====== MODE GIỜ (trong 1 ngày) ======
async function readCsvFilteredByDate(dateFilter) {
  if (!dateFilter) {
    const zeros = new Array(24).fill(0);
    return {
      labels: Array.from({ length: 24 }, (_, i) => String(i + 1)),
      buyData: zeros.slice(),
      sellData: zeros.slice(),
      buyCost: zeros.slice(),
      sellCost: zeros.slice(),
    };
  }

  const yearFromDate = dateFilter.split("-")[0];
  const csvUrl = getCsvUrlFromYear(yearFromDate);

  const res = await fetch(csvUrl + "?t=" + Date.now());
  const text = await res.text();

  const lines = text.trim().split(/\r?\n/);
  if (lines.length <= 1) {
    console.error("CSV không có dữ liệu");
    const zeros = new Array(24).fill(0);
    return {
      labels: Array.from({ length: 24 }, (_, i) => String(i + 1)),
      buyData: zeros.slice(),
      sellData: zeros.slice(),
      buyCost: zeros.slice(),
      sellCost: zeros.slice(),
    };
  }

  const header = lines[0].split(",");
  const idxDate = header.indexOf("date");
  const idxHour = header.indexOf("hour");
  const idxBuyHour = header.indexOf("buy_hour");
  const idxBuyHourCost = header.indexOf("buy_hour_cost");
  const idxSellHour = header.indexOf("sell_hour");
  const idxSellHourCost = header.indexOf("sell_hour_cost");

  if (idxDate < 0 || idxHour < 0 || idxBuyHour < 0 || idxSellHour < 0) {
    console.error("Thiếu cột giờ (date/hour/buy_hour/sell_hour)");
    const zeros = new Array(24).fill(0);
    return {
      labels: Array.from({ length: 24 }, (_, i) => String(i + 1)),
      buyData: zeros.slice(),
      sellData: zeros.slice(),
      buyCost: zeros.slice(),
      sellCost: zeros.slice(),
    };
  }

  const labels = Array.from({ length: 24 }, (_, i) => String(i + 1));
  const buyData = new Array(24).fill(0);
  const sellData = new Array(24).fill(0);
  const buyCost = new Array(24).fill(0);
  const sellCost = new Array(24).fill(0);

  for (let i = 1; i < lines.length; i++) {
    const line = lines[i].trim();
    if (!line) continue;

    const cols = line.split(",");
    if (cols.length < header.length) continue;

    const dateStr = cols[idxDate];
    const hourStr = cols[idxHour];

    if (dateStr !== dateFilter) continue;

    const hourInt = parseInt(hourStr, 10);
    if (Number.isNaN(hourInt) || hourInt < 1 || hourInt > 24) continue;

    const buyVal = parseFloat(cols[idxBuyHour]);
    const sellVal = parseFloat(cols[idxSellHour]);
    const buyCostVal =
      idxBuyHourCost >= 0 ? parseFloat(cols[idxBuyHourCost]) : 0;
    const sellCostVal =
      idxSellHourCost >= 0 ? parseFloat(cols[idxSellHourCost]) : 0;

    const idx = hourInt - 1;

    if (!Number.isNaN(buyVal)) buyData[idx] = buyVal;
    if (!Number.isNaN(sellVal)) sellData[idx] = sellVal;
    if (!Number.isNaN(buyCostVal)) buyCost[idx] = buyCostVal;
    if (!Number.isNaN(sellCostVal)) sellCost[idx] = sellCostVal;
  }

  return { labels, buyData, sellData, buyCost, sellCost };
}

// ====== MODE NGÀY (trong 1 tháng) ======
async function readCsvByMonth(monthFilter) {
  if (!monthFilter) {
    const defaultDays = 31;
    const zeros = new Array(defaultDays).fill(0);
    return {
      labels: Array.from({ length: defaultDays }, (_, i) => String(i + 1)),
      buyData: zeros.slice(),
      sellData: zeros.slice(),
      buyCost: zeros.slice(),
      sellCost: zeros.slice(),
    };
  }

  const yearFromMonth = monthFilter.split("-")[0];
  const csvUrl = getCsvUrlFromYear(yearFromMonth);

  const res = await fetch(csvUrl + "?t=" + Date.now());
  const text = await res.text();

  const lines = text.trim().split(/\r?\n/);
  if (lines.length <= 1) {
    console.error("CSV không có dữ liệu");
    const defaultDays = getDaysInMonth(monthFilter);
    const zeros = new Array(defaultDays).fill(0);
    return {
      labels: Array.from({ length: defaultDays }, (_, i) => String(i + 1)),
      buyData: zeros.slice(),
      sellData: zeros.slice(),
      buyCost: zeros.slice(),
      sellCost: zeros.slice(),
    };
  }

  const header = lines[0].split(",");
  const idxDate = header.indexOf("date");
  const idxBuyDay = header.indexOf("buy_day");
  const idxBuyDayCost = header.indexOf("buy_day_cost");
  const idxSellDay = header.indexOf("sell_day");
  const idxSellDayCost = header.indexOf("sell_day_cost");

  if (idxDate < 0 || idxBuyDay < 0 || idxSellDay < 0) {
    console.error("Thiếu cột 'date','buy_day','sell_day'");
    const defaultDays = getDaysInMonth(monthFilter);
    const zeros = new Array(defaultDays).fill(0);
    return {
      labels: Array.from({ length: defaultDays }, (_, i) => String(i + 1)),
      buyData: zeros.slice(),
      sellData: zeros.slice(),
      buyCost: zeros.slice(),
      sellCost: zeros.slice(),
    };
  }

  const daysInMonth = getDaysInMonth(monthFilter);
  const labels = Array.from({ length: daysInMonth }, (_, i) => String(i + 1));
  const buyData = new Array(daysInMonth).fill(0);
  const sellData = new Array(daysInMonth).fill(0);
  const buyCost = new Array(daysInMonth).fill(0);
  const sellCost = new Array(daysInMonth).fill(0);

  const prefix = monthFilter + "-";

  for (let i = 1; i < lines.length; i++) {
    const line = lines[i].trim();
    if (!line) continue;

    const cols = line.split(",");
    if (cols.length < header.length) continue;

    const dateStr = cols[idxDate];
    if (!dateStr.startsWith(prefix)) continue;

    const dParts = dateStr.split("-");
    if (dParts.length !== 3) continue;

    const dayInt = parseInt(dParts[2], 10);
    if (Number.isNaN(dayInt) || dayInt < 1 || dayInt > daysInMonth) continue;

    const buyVal = parseFloat(cols[idxBuyDay]);
    const sellVal = parseFloat(cols[idxSellDay]);
    const buyCostVal =
      idxBuyDayCost >= 0 ? parseFloat(cols[idxBuyDayCost]) : 0;
    const sellCostVal =
      idxSellDayCost >= 0 ? parseFloat(cols[idxSellDayCost]) : 0;

    const idx = dayInt - 1;

    if (!Number.isNaN(buyVal)) buyData[idx] = buyVal;
    if (!Number.isNaN(sellVal)) sellData[idx] = sellVal;
    if (!Number.isNaN(buyCostVal)) buyCost[idx] = buyCostVal;
    if (!Number.isNaN(sellCostVal)) sellCost[idx] = sellCostVal;
  }

  return { labels, buyData, sellData, buyCost, sellCost };
}

// ====== MODE THÁNG (12 tháng trong 1 năm) ======
async function readCsvByYear(yearFilter) {
  if (!yearFilter) {
    const labels = Array.from({ length: 12 }, (_, i) => String(i + 1));
    const zeros = new Array(12).fill(0);
    return {
      labels,
      buyData: zeros.slice(),
      sellData: zeros.slice(),
      buyCost: zeros.slice(),
      sellCost: zeros.slice(),
    };
  }

  const csvUrl = getCsvUrlFromYear(yearFilter);

  const res = await fetch(csvUrl + "?t=" + Date.now());
  const text = await res.text();

  const lines = text.trim().split(/\r?\n/);
  if (lines.length <= 1) {
    console.error("CSV không có dữ liệu");
    const labels = Array.from({ length: 12 }, (_, i) => String(i + 1));
    const zeros = new Array(12).fill(0);
    return {
      labels,
      buyData: zeros.slice(),
      sellData: zeros.slice(),
      buyCost: zeros.slice(),
      sellCost: zeros.slice(),
    };
  }

  const header = lines[0].split(",");
  const idxDate = header.indexOf("date");
  const idxBuyMonth = header.indexOf("buy_month");
  const idxBuyMonthCost = header.indexOf("buy_month_cost");
  const idxSellMonth = header.indexOf("sell_month");
  const idxSellMonthCost = header.indexOf("sell_month_cost");

  if (idxDate < 0 || idxBuyMonth < 0 || idxSellMonth < 0) {
    console.error("Thiếu cột 'date','buy_month','sell_month'");
    const labels = Array.from({ length: 12 }, (_, i) => String(i + 1));
    const zeros = new Array(12).fill(0);
    return {
      labels,
      buyData: zeros.slice(),
      sellData: zeros.slice(),
      buyCost: zeros.slice(),
      sellCost: zeros.slice(),
    };
  }

  const labels = Array.from({ length: 12 }, (_, i) => String(i + 1));
  const buyData = new Array(12).fill(0);
  const sellData = new Array(12).fill(0);
  const buyCost = new Array(12).fill(0);
  const sellCost = new Array(12).fill(0);

  const prefixYear = String(yearFilter) + "-";

  for (let i = 1; i < lines.length; i++) {
    const line = lines[i].trim();
    if (!line) continue;

    const cols = line.split(",");
    if (cols.length < header.length) continue;

    const dateStr = cols[idxDate];
    if (!dateStr.startsWith(prefixYear)) continue;

    const dParts = dateStr.split("-");
    if (dParts.length !== 3) continue;

    const monthInt = parseInt(dParts[1], 10);
    if (Number.isNaN(monthInt) || monthInt < 1 || monthInt > 12) continue;

    const buyVal = parseFloat(cols[idxBuyMonth]);
    const sellVal = parseFloat(cols[idxSellMonth]);
    const buyCostVal =
      idxBuyMonthCost >= 0 ? parseFloat(cols[idxBuyMonthCost]) : 0;
    const sellCostVal =
      idxSellMonthCost >= 0 ? parseFloat(cols[idxSellMonthCost]) : 0;

    const idx = monthInt - 1;

    if (!Number.isNaN(buyVal)) buyData[idx] = buyVal;
    if (!Number.isNaN(sellVal)) sellData[idx] = sellVal;
    if (!Number.isNaN(buyCostVal)) buyCost[idx] = buyCostVal;
    if (!Number.isNaN(sellCostVal)) sellCost[idx] = sellCostVal;
  }

  return { labels, buyData, sellData, buyCost, sellCost };
}

// ====== MODE NĂM (tổng từng năm theo file) ======
async function readCsvYearSum() {
  if (!AVAILABLE_YEARS.length) {
    const year = new Date().getFullYear();
    AVAILABLE_YEARS = [year];
  }

  const labels = AVAILABLE_YEARS.map((y) => String(y));
  const buyData = new Array(labels.length).fill(0);
  const sellData = new Array(labels.length).fill(0);
  const buyCost = new Array(labels.length).fill(0);
  const sellCost = new Array(labels.length).fill(0);

  for (let i = 0; i < AVAILABLE_YEARS.length; i++) {
    const year = AVAILABLE_YEARS[i];
    const csvUrl = getCsvUrlFromYear(String(year));
    try {
      const res = await fetch(csvUrl + "?t=" + Date.now());
      if (!res.ok) continue;
      const text = await res.text();
      const lines = text.trim().split(/\r?\n/);
      if (lines.length <= 1) continue;

      const header = lines[0].split(",");
      const idxBuyYear = header.indexOf("buy_year");
      const idxBuyYearCost = header.indexOf("buy_year_cost");
      const idxSellYear = header.indexOf("sell_year");
      const idxSellYearCost = header.indexOf("sell_year_cost");

      if (idxBuyYear < 0 || idxSellYear < 0) continue;

      let lastDataLine = null;
      for (let j = lines.length - 1; j >= 1; j--) {
        const ln = lines[j].trim();
        if (!ln) continue;
        lastDataLine = ln;
        break;
      }
      if (!lastDataLine) continue;

      const cols = lastDataLine.split(",");
      if (cols.length < header.length) continue;

      const buyVal = parseFloat(cols[idxBuyYear]);
      const sellVal = parseFloat(cols[idxSellYear]);
      const buyCostVal =
        idxBuyYearCost >= 0 ? parseFloat(cols[idxBuyYearCost]) : 0;
      const sellCostVal =
        idxSellYearCost >= 0 ? parseFloat(cols[idxSellYearCost]) : 0;

      if (!Number.isNaN(buyVal)) buyData[i] = buyVal;
      if (!Number.isNaN(sellVal)) sellData[i] = sellVal;
      if (!Number.isNaN(buyCostVal)) buyCost[i] = buyCostVal;
      if (!Number.isNaN(sellCostVal)) sellCost[i] = sellCostVal;
    } catch (e) {
      console.error("Lỗi đọc năm", year, e);
    }
  }

  return { labels, buyData, sellData, buyCost, sellCost };
}

function setupLegendClicks() {
  const legendItems = document.querySelectorAll("#legendCustom .legend-item");
  legendItems.forEach((item) => {
    item.addEventListener("click", () => {
      if (!chart) return;
      const idx = parseInt(item.getAttribute("data-dataset-index"), 10);
      const ds = chart.data.datasets[idx];
      ds.hidden = !ds.hidden;
      item.classList.toggle("disabled", !!ds.hidden);
      chart.update();
    });
  });
}

function updateModeUI() {
  const dateWrapper = document.getElementById("dateWrapper");
  const monthWrapper = document.getElementById("monthWrapper");
  const yearWrapper = document.getElementById("yearWrapper");

  const btnDay = document.querySelector('.mode-btn[data-mode="day"]');
  const btnMonth = document.querySelector('.mode-btn[data-mode="month"]');
  const btnYear = document.querySelector('.mode-btn[data-mode="year"]');
  const btnYearSum = document.querySelector('.mode-btn[data-mode="yearsum"]');

  if (currentMode === "day") {
    dateWrapper.style.display = "inline-flex";
    monthWrapper.style.display = "none";
    yearWrapper.style.display = "none";

    btnDay?.classList.add("active");
    btnMonth?.classList.remove("active");
    btnYear?.classList.remove("active");
    btnYearSum?.classList.remove("active");

    updateDateDisplay(currentDate || "");
  } else if (currentMode === "month") {
    dateWrapper.style.display = "none";
    monthWrapper.style.display = "inline-flex";
    yearWrapper.style.display = "none";

    btnDay?.classList.remove("active");
    btnMonth?.classList.add("active");
    btnYear?.classList.remove("active");
    btnYearSum?.classList.remove("active");

    updateMonthDisplay(currentMonth || "");
  } else if (currentMode === "year") {
    dateWrapper.style.display = "none";
    monthWrapper.style.display = "none";
    yearWrapper.style.display = "inline-flex";

    btnDay?.classList.remove("active");
    btnMonth?.classList.remove("active");
    btnYear?.classList.add("active");
    btnYearSum?.classList.remove("active");

    updateYearDisplay(currentYear || "");
  } else {
    dateWrapper.style.display = "none";
    monthWrapper.style.display = "none";
    yearWrapper.style.display = "none";

    btnDay?.classList.remove("active");
    btnMonth?.classList.remove("active");
    btnYear?.classList.remove("active");
    btnYearSum?.classList.add("active");

    updateYearSumFooter();
  }
}

async function setMode(mode) {
  if (!isValidMode(mode)) mode = "year";

  currentMode = mode;
  updateModeUI();
  saveSettings();
  await refreshChart();
}

async function initChart() {
  await detectAvailableYears();
  populateYearOptions();

  const saved = loadSettings();
  if (saved.mode && isValidMode(saved.mode)) {
    currentMode = saved.mode;
  } else {
    currentMode = "year";
  }

  ensureDefaultDate(saved.date);
  ensureDefaultMonth(saved.month);
  ensureDefaultYear(saved.year);

  updateModeUI();

  let data;
  if (currentMode === "day") {
    data = await readCsvFilteredByDate(currentDate);
  } else if (currentMode === "month") {
    data = await readCsvByMonth(currentMonth);
  } else if (currentMode === "year") {
    data = await readCsvByYear(currentYear);
  } else {
    data = await readCsvYearSum();
  }

  const { labels, buyData, sellData, buyCost, sellCost } = data;
  const ctx = document.getElementById("evnChart").getContext("2d");

  // FONT responsive: PC to hơn
  const viewportW =
    window.innerWidth || document.documentElement.clientWidth || 0;
  const isDesktop = viewportW >= 900;

  const tickFontSize = isDesktop ? 14 : 11;
  const kwhLabelSize = isDesktop ? 14 : 11;
  const axisTitleSize = isDesktop ? 14 : 12;
  // costLabelSize giờ KHÔNG dùng nữa (thay bằng hàm động)

  const gridColor =
    getComputedStyle(document.documentElement).getPropertyValue(
      "--grid-color"
    ) || "rgba(156,163,175,0.6)";
  const axisColor =
    getComputedStyle(document.documentElement).getPropertyValue(
      "--axis-text"
    ) || "#4b5563";
  const labelColor =
    getComputedStyle(document.documentElement).getPropertyValue(
      "--label-text"
    ) || "#111827";

  chart = new Chart(ctx, {
    type: "bar",
    data: {
      labels: labels,
      datasets: [
        {
          label: "Mua",
          data: buyData,
          costData: buyCost,
          borderWidth: 1,
          backgroundColor: makeBuyColors(buyData),
          borderColor: "rgba(88, 28, 135, 0.9)",
          borderRadius: 4,
          categoryPercentage: 0.9,
          barPercentage: 1.0,
        },
        {
          label: "Bán",
          data: sellData,
          costData: sellCost,
          borderWidth: 1,
          backgroundColor: makeSellColors(sellData),
          borderColor: "rgba(15, 23, 42, 0.9)",
          borderRadius: 4,
          categoryPercentage: 0.9,
          barPercentage: 1.0,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: {
        duration: 500,
        easing: "easeOutCubic",
      },
      layout: { padding: { left: 0, right: 0, top: 0, bottom: 0 } },
      scales: {
        x: {
          grid: { display: false },
          ticks: {
            color: axisColor,
            font: { size: tickFontSize },
          },
          title: { display: false },
        },
        y: {
          beginAtZero: true,
          // Chừa khoảng trống ~15% trên đỉnh để số kWh không bị cắt
          grace: "15%",
          grid: { color: gridColor },
          ticks: {
            color: axisColor,
            font: { size: tickFontSize },
          },
          title: {
            display: true,
            text: "kWh",
            color: axisColor,
            font: { size: axisTitleSize, weight: "500" },
          },
        },
      },
      plugins: {
        legend: { display: false },
        datalabels: {
          clip: false, // cho phép chữ vươn ra ngoài vùng chart, không bị cắt
          labels: {
            kwh: {
              color: labelColor,
              anchor: "end",
              align: "end",
              rotation: 0,
              formatter(value) {
                return formatKwhValue(value);
              },
              font: { size: kwhLabelSize, weight: "400" },
              offset: 2,
            },
            cost: {
              color: labelColor,
              anchor: "center",
              align: "center",
              rotation: -90,
              clamp: true,
              formatter(value, context) {
                const ds = context.dataset;
                const idx = context.dataIndex;
                const costArr = ds.costData || [];
                const cost = costArr[idx];
                return formatMoneyValue(cost);
              },
              // ====== FONT ĐỘNG: chiều cao chữ ~ bề rộng cột ======
              font: (ctx) => {
                const chart = ctx.chart;
                const meta = chart.getDatasetMeta(ctx.datasetIndex);
                const el = meta && meta.data ? meta.data[ctx.dataIndex] : null;
                let barWidth = 10;

                if (el) {
                  // Chart.js 3/4: BarElement thường có width
                  if (typeof el.width === "number") {
                    barWidth = el.width;
                  } else if (el._model && typeof el._model.width === "number") {
                    barWidth = el._model.width;
                  }
                }

                // Chiều cao chữ ≈ 60% độ rộng cột, kẹp trong khoảng 8–20 px
                let size = barWidth * 0.6;
                if (!isFinite(size) || size <= 0) size = 10;
                size = Math.max(8, Math.min(size, 20));

                return {
                  size,
                  weight: "400",
                };
              },
              offset: 0,
            },
          },
        },
        tooltip: {
          enabled: true,
          backgroundColor: "rgba(15, 23, 42, 0.95)",
          titleColor: "#e5e7eb",
          bodyColor: "#e5e7eb",
          borderColor: "rgba(55,65,81,0.8)",
          borderWidth: 1,
          padding: 8,
          displayColors: true,
          callbacks: {
            title(items) {
              if (!items || !items.length) return "";
              const item = items[0];
              const label = item.label;

              if (currentMode === "day") {
                const hour = parseInt(label, 10);
                if (Number.isNaN(hour)) return label;
                const start = hour - 1;
                const end = hour;
                return `${start}h -> ${end}h`;
              } else if (currentMode === "month") {
                return `Ngày ${label}`;
              } else if (currentMode === "year") {
                return `Tháng ${label}`;
              } else if (currentMode === "yearsum") {
                return `Năm ${label}`;
              }
              return label;
            },
            label(context) {
              const v = context.parsed.y || 0;
              const ds = context.dataset;
              const idx = context.dataIndex;
              const costArr = ds.costData || [];
              const cost = costArr[idx] || 0;
              const parts = [];

              parts.push(
                ` ${context.dataset.label}: ${formatTooltipKwh(v)} kWh`
              );
              if (cost > 0) {
                parts.push(`  ■ Giá: ${formatTooltipMoney(cost)} K`);
              }
              return parts;
            },
          },
        },
        zoom: {
          pan: { enabled: false },
          zoom: {
            wheel: { enabled: false },
            pinch: { enabled: true },
            drag: { enabled: false },
            mode: "x",
          },
        },
      },
    },
  });

  setupLegendClicks();
  updateModeUI();
  saveSettings();
}

async function refreshChart() {
  if (!chart) return;

  let data;
  if (currentMode === "day") {
    if (!currentDate) ensureDefaultDate();
    data = await readCsvFilteredByDate(currentDate);
  } else if (currentMode === "month") {
    if (!currentMonth) ensureDefaultMonth();
    data = await readCsvByMonth(currentMonth);
  } else if (currentMode === "year") {
    if (!currentYear) ensureDefaultYear();
    data = await readCsvByYear(currentYear);
  } else {
    data = await readCsvYearSum();
  }

  const { labels, buyData, sellData, buyCost, sellCost } = data;

  chart.data.labels = labels;
  chart.data.datasets[0].data = buyData;
  chart.data.datasets[1].data = sellData;
  chart.data.datasets[0].costData = buyCost;
  chart.data.datasets[1].costData = sellCost;
  chart.data.datasets[0].backgroundColor = makeBuyColors(buyData);
  chart.data.datasets[1].backgroundColor = makeSellColors(sellData);

  chart.update();
}

(async () => {
  const dateInput = document.getElementById("datePicker");
  const monthInput = document.getElementById("monthPicker");
  const yearInput = document.getElementById("yearPicker");
  const btnDay = document.querySelector('.mode-btn[data-mode="day"]');
  const btnMonth = document.querySelector('.mode-btn[data-mode="month"]');
  const btnYear = document.querySelector('.mode-btn[data-mode="year"]');
  const btnYearSum = document.querySelector('.mode-btn[data-mode="yearsum"]');

  const onDateChange = () => {
    const v = dateInput.value;
    if (!v) return;
    currentDate = v;
    saveSettings();
    if (currentMode === "day") {
      updateDateDisplay(currentDate);
      refreshChart().catch(console.error);
    }
  };

  const onMonthChange = () => {
    const v = monthInput.value;
    if (!v) return;
    currentMonth = v;
    saveSettings();
    if (currentMode === "month") {
      updateMonthDisplay(currentMonth);
      refreshChart().catch(console.error);
    }
  };

  const onYearChange = () => {
    const v = yearInput.value;
    if (!v) return;
    currentYear = v;
    saveSettings();
    if (currentMode === "year") {
      updateYearDisplay(currentYear);
      refreshChart().catch(console.error);
    }
  };

  dateInput.addEventListener("change", onDateChange);
  dateInput.addEventListener("input", onDateChange);

  monthInput.addEventListener("change", onMonthChange);
  monthInput.addEventListener("input", onMonthChange);

  yearInput.addEventListener("change", onYearChange);
  yearInput.addEventListener("input", onYearChange);

  btnDay?.addEventListener("click", () =>
    setMode("day").catch(console.error)
  );
  btnMonth?.addEventListener("click", () =>
    setMode("month").catch(console.error)
  );
  btnYear?.addEventListener("click", () =>
    setMode("year").catch(console.error)
  );
  btnYearSum?.addEventListener("click", () =>
    setMode("yearsum").catch(console.error)
  );

  await initChart();

  setInterval(() => {
    refreshChart().catch(console.error);
  }, REFRESH_MS);
})().catch(console.error);