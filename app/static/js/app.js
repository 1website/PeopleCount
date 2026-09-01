/**
 * Cambodia Population & Family Census Management System - Core Application
 */

// Global App State
const state = {
  currentUser: null,
  geoTree: [],
  selectedGeo: {
    provinceId: null,
    districtId: null,
    communeId: null,
    villageId: null
  },
  familiesList: [],
  familiesCurrentPage: 1,
  familiesPageSize: 15,
  currentTab: "dashboard"
};

// Register Service Worker for PWA
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/static/sw.js?v=2.3")
      .then(reg => {
        console.log("[PWA] Service Worker registered:", reg.scope);
        reg.update();
        reg.addEventListener("updatefound", () => {
          const newWorker = reg.installing;
          if (newWorker) {
            newWorker.addEventListener("statechange", () => {
              if (newWorker.state === "installed" && navigator.serviceWorker.controller) {
                console.log("[PWA] New version detected, reloading page...");
                window.location.reload();
              }
            });
          }
        });
      })
      .catch(err => console.warn("[PWA] Service Worker failed:", err));
  });
}

// --- Toast System ---
window.showToast = function(message, type = "info") {
  let container = document.getElementById("toast-container");
  if (!container) {
    container = document.createElement("div");
    container.id = "toast-container";
    container.className = "toast-container";
    document.body.appendChild(container);
  }

  const toast = document.createElement("div");
  toast.className = `toast ${type}`;
  let icon = "fa-circle-info";
  if (type === "success") icon = "fa-circle-check";
  if (type === "error") icon = "fa-circle-exclamation";
  
  toast.innerHTML = `<i class="fa-solid ${icon}"></i> <span>${message}</span>`;
  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = "0";
    toast.style.transform = "translateX(20px)";
    setTimeout(() => toast.remove(), 300);
  }, 3500);
};

// --- Khmer Date & Number Formatter Helpers ---
const KHMER_DIGITS = ['០', '១', '២', '៣', '៤', '៥', '៦', '៧', '៨', '៩'];
const KHMER_DAYS = ['អាទិត្យ', 'ច័ន្ទ', 'អង្គារ', 'ពុធ', 'ព្រហស្បតិ៍', 'សុក្រ', 'សៅរ៍'];
const KHMER_MONTHS = [
  'មករា', 'កុម្ភៈ', 'មីនា', 'មេសា', 'ឧសភា', 'មិថុនា',
  'កក្កដា', 'សីហា', 'កញ្ញា', 'តុលា', 'វិច្ឆិកា', 'ធ្នូ'
];

function toKhmerDigits(num) {
  return String(num).replace(/[0-9]/g, d => KHMER_DIGITS[d]);
}

function formatKhmerFullDate(date = new Date()) {
  const dayName = KHMER_DAYS[date.getDay()];
  const day = toKhmerDigits(date.getDate());
  const month = KHMER_MONTHS[date.getMonth()];
  const year = toKhmerDigits(date.getFullYear());
  return `ថ្ងៃ${dayName} ទី${day} ខែ${month} ឆ្នាំ${year}`;
}

// --- Auth & API Request Helpers ---
async function apiRequest(url, options = {}) {
  const token = localStorage.getItem("access_token");
  const headers = options.headers || {};
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  if (!headers["Content-Type"] && !(options.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
  }
  options.headers = headers;

  try {
    const res = await fetch(url, options);
    if (res.status === 401) {
      console.warn("Session expired or unauthorized");
    }
    return res;
  } catch (err) {
    console.error("Fetch failed (possibly offline):", err);
    throw err;
  }
}

// --- Age Calculation Helper ---
function calculateAgeFromDob(dobStr) {
  if (!dobStr) return 0;
  const dob = new Date(dobStr);
  if (isNaN(dob.getTime())) return 0;
  const today = new Date();
  let age = today.getFullYear() - dob.getFullYear();
  const m = today.getMonth() - dob.getMonth();
  if (m < 0 || (m === 0 && today.getDate() < dob.getDate())) {
    age--;
  }
  return Math.max(0, age);
}

// --- Geographic Hierarchy Loader ---
async function loadGeographicHierarchy() {
  try {
    if (navigator.onLine) {
      const res = await apiRequest("/api/geo/full-hierarchy");
      if (res.ok) {
        state.geoTree = await res.json();
        await window.censusDB.saveCachedGeo(state.geoTree);
      }
    } else {
      // Offline: load cached hierarchy from IndexedDB
      const cached = await window.censusDB.getCachedGeo();
      if (cached) {
        state.geoTree = cached;
        console.log("[Offline] Loaded cached geo hierarchy");
      }
    }
  } catch (err) {
    const cached = await window.censusDB.getCachedGeo();
    if (cached) state.geoTree = cached;
  }
  populateGeoDropdowns();
}

function populateGeoDropdowns() {
  // 1. Dashboard filters
  const provSelect = document.getElementById("filter-province");
  if (provSelect) {
    provSelect.innerHTML = `<option value="">-- គ្រប់ខេត្ត/រាជធានី --</option>` +
      state.geoTree.map(p => `<option value="${p.id}">${p.name_kh} (${p.code})</option>`).join("");
  }

  // 2. Form village selection
  populateFormGeo();
}

function populateFormGeo() {
  const fProv = document.getElementById("form-province");
  const fDist = document.getElementById("form-district");
  const fComm = document.getElementById("form-commune");
  const fVill = document.getElementById("form-village");
  if (!fProv) return;

  fProv.innerHTML = `<option value="">-- ជ្រើសរើសខេត្ត/រាជធានី --</option>` +
    state.geoTree.map(p => `<option value="${p.id}">${p.name_kh} (${p.code})</option>`).join("");

  // Auto-select when single locality exists (ភូមិប្រាសាទត្រាវ ឃុំគោកដូង ស្រុកអង្គរជុំ ខេត្តសៀមរាប)
  if (state.geoTree.length === 1) {
    const prov = state.geoTree[0];
    fProv.value = prov.id;
    if (fDist && prov.districts.length === 1) {
      const dist = prov.districts[0];
      fDist.innerHTML = `<option value="${dist.id}" selected>${dist.name_kh} (${dist.code})</option>`;
      if (fComm && dist.communes.length === 1) {
        const comm = dist.communes[0];
        fComm.innerHTML = `<option value="${comm.id}" selected>${comm.name_kh} (${comm.code})</option>`;
        if (fVill && comm.villages.length === 1) {
          const vill = comm.villages[0];
          fVill.innerHTML = `<option value="${vill.id}" data-code="${vill.code}" selected>${vill.name_kh} (${vill.code})</option>`;
          updatePreviewFamilyCode();
        }
      }
    }
  }
}

// Cascade Event Listeners
function setupGeoCascade() {
  // Form cascades
  const fProv = document.getElementById("form-province");
  const fDist = document.getElementById("form-district");
  const fComm = document.getElementById("form-commune");
  const fVill = document.getElementById("form-village");

  if (fProv) {
    fProv.addEventListener("change", (e) => {
      const pId = parseInt(e.target.value);
      fDist.innerHTML = `<option value="">-- ជ្រើសរើសស្រុក/ខណ្ឌ --</option>`;
      fComm.innerHTML = `<option value="">-- ជ្រើសរើសឃុំ/សង្កាត់ --</option>`;
      fVill.innerHTML = `<option value="">-- ជ្រើសរើសភូមិ --</option>`;
      const prov = state.geoTree.find(p => p.id === pId);
      if (prov) {
        fDist.innerHTML += prov.districts.map(d => `<option value="${d.id}">${d.name_kh} (${d.code})</option>`).join("");
      }
      updatePreviewFamilyCode();
    });
  }

  if (fDist) {
    fDist.addEventListener("change", (e) => {
      const dId = parseInt(e.target.value);
      fComm.innerHTML = `<option value="">-- ជ្រើសរើសឃុំ/សង្កាត់ --</option>`;
      fVill.innerHTML = `<option value="">-- ជ្រើសរើសភូមិ --</option>`;
      for (const p of state.geoTree) {
        const dist = p.districts.find(d => d.id === dId);
        if (dist) {
          fComm.innerHTML += dist.communes.map(c => `<option value="${c.id}">${c.name_kh} (${c.code})</option>`).join("");
          break;
        }
      }
      updatePreviewFamilyCode();
    });
  }

  if (fComm) {
    fComm.addEventListener("change", (e) => {
      const cId = parseInt(e.target.value);
      fVill.innerHTML = `<option value="">-- ជ្រើសរើសភូមិ --</option>`;
      for (const p of state.geoTree) {
        for (const d of p.districts) {
          const comm = d.communes.find(c => c.id === cId);
          if (comm) {
            fVill.innerHTML += comm.villages.map(v => `<option value="${v.id}" data-code="${v.code}">${v.name_kh} (${v.code})</option>`).join("");
            break;
          }
        }
      }
      updatePreviewFamilyCode();
    });
  }

  if (fVill) {
    fVill.addEventListener("change", updatePreviewFamilyCode);
  }

  // Dashboard filter cascades
  const dProv = document.getElementById("filter-province");
  const dDist = document.getElementById("filter-district");
  const dComm = document.getElementById("filter-commune");
  const dVill = document.getElementById("filter-village");

  if (dProv) {
    dProv.addEventListener("change", (e) => {
      const pId = parseInt(e.target.value);
      dDist.innerHTML = `<option value="">-- គ្រប់ស្រុក/ខណ្ឌ --</option>`;
      dComm.innerHTML = `<option value="">-- គ្រប់ឃុំ/សង្កាត់ --</option>`;
      dVill.innerHTML = `<option value="">-- គ្រប់ភូមិ --</option>`;
      const prov = state.geoTree.find(p => p.id === pId);
      if (prov) {
        dDist.innerHTML += prov.districts.map(d => `<option value="${d.id}">${d.name_kh}</option>`).join("");
      }
      loadDashboardStats();
    });
  }

  if (dDist) {
    dDist.addEventListener("change", (e) => {
      const dId = parseInt(e.target.value);
      dComm.innerHTML = `<option value="">-- គ្រប់ឃុំ/សង្កាត់ --</option>`;
      dVill.innerHTML = `<option value="">-- គ្រប់ភូមិ --</option>`;
      for (const p of state.geoTree) {
        const dist = p.districts.find(d => d.id === dId);
        if (dist) {
          dComm.innerHTML += dist.communes.map(c => `<option value="${c.id}">${c.name_kh}</option>`).join("");
          break;
        }
      }
      loadDashboardStats();
    });
  }

  if (dComm) {
    dComm.addEventListener("change", (e) => {
      const cId = parseInt(e.target.value);
      dVill.innerHTML = `<option value="">-- គ្រប់ភូមិ --</option>`;
      for (const p of state.geoTree) {
        for (const d of p.districts) {
          const comm = d.communes.find(c => c.id === cId);
          if (comm) {
            dVill.innerHTML += comm.villages.map(v => `<option value="${v.id}">${v.name_kh}</option>`).join("");
            break;
          }
        }
      }
      loadDashboardStats();
    });
  }

  if (dVill) {
    dVill.addEventListener("change", () => loadDashboardStats());
  }
}

function updatePreviewFamilyCode() {
  const fVill = document.getElementById("form-village");
  const codeEl = document.getElementById("preview-family-code");
  if (!codeEl) return;
  const selectedOpt = fVill?.options[fVill.selectedIndex];
  if (selectedOpt && selectedOpt.value) {
    const vCode = selectedOpt.getAttribute("data-code");
    codeEl.innerHTML = `<span class="badge-tag general">កូដគ្រួសារស្វ័យប្រវត្តិ៖ <strong>FAM-${vCode}-XXXX</strong></span>`;
  } else {
    codeEl.innerHTML = `<span class="text-dim">ជ្រើសរើសភូមិដើម្បីបង្កើតលេខកូដសម្គាល់គ្រួសារ (Family ID)</span>`;
  }
}

// --- Navigation Tabs ---
const TAB_TITLES = {
  "dashboard": `<i class="fa-solid fa-chart-pie" style="color: var(--gold-light); margin-right: 8px;"></i> ផ្ទាំងគ្រប់គ្រងស្ថិតិប្រជាជន និងគ្រួសារកម្ពុជា`,
  "registration": `<i class="fa-solid fa-user-plus" style="color: var(--gold-light); margin-right: 8px;"></i> ទម្រង់ចុះឈ្មោះគ្រួសារ និងបញ្ចូលសមាជិក`,
  "families": `<i class="fa-solid fa-address-book" style="color: var(--gold-light); margin-right: 8px;"></i> បញ្ជីគ្រប់គ្រងគ្រួសារ និងពិនិត្យអនុម័ត`,
  "geo": `<i class="fa-solid fa-sitemap" style="color: var(--gold-light); margin-right: 8px;"></i> រចនាសម្ព័ន្ធរដ្ឋបាលភូមិសាស្ត្រកម្ពុជា ៤ ថ្នាក់`,
  "reports": `<i class="fa-solid fa-file-excel" style="color: var(--gold-light); margin-right: 8px;"></i> របាយការណ៍ និងនាំចេញឯកសាររដ្ឋបាល`,
  "users": `<i class="fa-solid fa-users-gear" style="color: var(--gold-light); margin-right: 8px;"></i> គ្រប់គ្រងអ្នកប្រើប្រាស់ និងសិទ្ធិ (User Management)`,
  "backup": `<i class="fa-solid fa-database" style="color: var(--gold-light); margin-right: 8px;"></i> បម្រុងទុក និងស្តារទិន្នន័យ (1-Click Backup & Restore)`
};

function switchTab(tabId) {
  // If user role is COLLECTOR (non-admin), restrict access to registration and families tabs
  if (state.currentUser && state.currentUser.role !== "ADMIN") {
    if (tabId !== "registration" && tabId !== "families") {
      tabId = "registration";
    }
  }

  state.currentTab = tabId;
  document.querySelectorAll(".nav-item").forEach(item => {
    item.classList.toggle("active", item.getAttribute("data-tab") === tabId);
  });
  document.querySelectorAll(".view-section").forEach(sec => {
    sec.classList.toggle("active", sec.id === `view-${tabId}`);
  });

  const titleEl = document.getElementById("topbar-page-title");
  if (titleEl && TAB_TITLES[tabId]) {
    titleEl.innerHTML = TAB_TITLES[tabId];
  }

  // Close mobile drawer if open
  document.getElementById("app-sidebar")?.classList.remove("open");

  if (tabId === "dashboard") loadDashboardStats();
  if (tabId === "registration") openRegistrationModal();
  if (tabId === "families") loadFamiliesList();
  if (tabId === "geo") loadGeoExplorer();
  if (tabId === "users") loadUsersList();
  if (tabId === "backup") loadBackupStats();
}

window.openRegistrationModal = function() {
  const modal = document.getElementById("family-registration-modal");
  if (!modal) return;
  modal.classList.add("active");
  const container = document.getElementById("form-members-container");
  if (!container || container.children.length === 0) {
    resetRegistrationForm();
  }
};

window.closeRegistrationModal = function() {
  document.getElementById("family-registration-modal")?.classList.remove("active");
};

window.refreshCurrentView = function() {
  if (state.currentTab === "dashboard") loadDashboardStats();
  if (state.currentTab === "families") loadFamiliesList();
};

// --- Dashboard View ---
async function loadDashboardStats() {
  try {
    const res = await apiRequest("/api/reports/dashboard-stats");
    if (!res.ok) return;
    const data = await res.json();
    renderDashboard(data);
  } catch (err) {
    console.warn("Could not load stats (offline):", err);
  }
}

function renderDashboard(data) {
  // Families KPI
  document.getElementById("kpi-families-total").textContent = (data.families.total || 0).toLocaleString();
  document.getElementById("kpi-poor1-count").textContent = (data.families.poor_1 || 0);
  document.getElementById("kpi-poor2-count").textContent = (data.families.poor_2 || 0);
  document.getElementById("kpi-general-count").textContent = (data.families.general || 0);

  // Demographics KPI
  const pop = data.demographics;
  document.getElementById("kpi-pop-total").textContent = (pop.total_population || 0).toLocaleString();
  document.getElementById("kpi-male-count").textContent = (pop.male || 0);
  document.getElementById("kpi-female-count").textContent = (pop.female || 0);
  document.getElementById("kpi-female-pct").textContent = pop.female_percentage + "%";

  // Gender progress bar
  const malePct = pop.total_population ? ((pop.male / pop.total_population) * 100).toFixed(1) : 50;
  const femalePct = pop.female_percentage || 50;
  const genderBar = document.getElementById("progress-gender-bar");
  if (genderBar) genderBar.style.width = `${femalePct}%`;
  document.getElementById("gender-ratio-text").textContent = `ស្រី: ${femalePct}% | ប្រុស: ${malePct}%`;

  // Birth Certificates KPI
  const bc = data.birth_certificate;
  document.getElementById("kpi-birthcert-pct").textContent = bc.percentage_have + "%";
  document.getElementById("kpi-birthcert-have").textContent = bc.have;
  document.getElementById("kpi-birthcert-none").textContent = bc.none;
  const bcBar = document.getElementById("progress-birthcert-bar");
  if (bcBar) bcBar.style.width = `${bc.percentage_have}%`;

  // Education & Dropouts
  const edu = data.education;
  document.getElementById("kpi-school-age").textContent = edu.total_school_age;
  const kpiInfants0 = document.getElementById("kpi-infants-0");
  if (kpiInfants0) kpiInfants0.textContent = edu.infants_0 || 0;
  const kpiSchoolSub = document.getElementById("kpi-school-age-sub");
  if (kpiSchoolSub) kpiSchoolSub.textContent = edu.total_school_age || 0;

  document.getElementById("kpi-dropouts-count").textContent = edu.dropouts_count;
  document.getElementById("kpi-dropout-rate").textContent = edu.dropout_rate_percent + "%";
  const dropBar = document.getElementById("progress-dropout-bar");
  if (dropBar) dropBar.style.width = `${edu.dropout_rate_percent}%`;

  // School Age Breakdown Table (រួមបញ្ចូលកុមារអាយុ ០ ឆ្នាំ)
  const eduTbody = document.getElementById("table-edu-breakdown");
  if (eduTbody) {
    eduTbody.innerHTML = `
      <tr style="background: rgba(56, 189, 248, 0.08); border-left: 3px solid #38bdf8;">
        <td>
          <i class="fa-solid fa-baby" style="color: #38bdf8; margin-right: 6px;"></i>
          <strong style="color: #7dd3fc;">ទារក/កុមារអាយុ ០ ឆ្នាំ (អាយុក្រោម ១ ឆ្នាំ)</strong>
        </td>
        <td class="text-right"><strong style="color: #38bdf8; font-size: 1.05rem;">${edu.infants_0 || 0}</strong> នាក់</td>
      </tr>
      <tr>
        <td>កុមារតូច (១-២ ឆ្នាំ)</td>
        <td class="text-right"><strong>${edu.toddlers_1_2 || 0}</strong> នាក់</td>
      </tr>
      <tr>
        <td>កុមារតូច (៣-៥ ឆ្នាំ)</td>
        <td class="text-right"><strong>${edu.kindergarten_3_5 || 0}</strong> នាក់</td>
      </tr>
      <tr>
        <td>កម្រិតបឋមសិក្សា (៦-១១ ឆ្នាំ)</td>
        <td class="text-right"><strong>${edu.primary_6_11 || 0}</strong> នាក់</td>
      </tr>
      <tr>
        <td>កម្រិតអនុវិទ្យាល័យ (១២-១៤ ឆ្នាំ)</td>
        <td class="text-right"><strong>${edu.lower_sec_12_14 || 0}</strong> នាក់</td>
      </tr>
      <tr>
        <td>កម្រិតវិទ្យាល័យ (១៥-១៧ ឆ្នាំ)</td>
        <td class="text-right"><strong>${edu.upper_sec_15_17 || 0}</strong> នាក់</td>
      </tr>
      <tr style="border-top: 1px solid var(--border-color);">
        <td><strong>កុមារសរុបដល់វ័យសិក្សា (៦-១៧ ឆ្នាំ)</strong></td>
        <td class="text-right"><strong>${edu.total_school_age || 0}</strong> នាក់</td>
      </tr>
      <tr style="border-top: 2px solid var(--border-color); color: var(--gold-light); background: rgba(245, 158, 11, 0.05);">
        <td><strong><i class="fa-solid fa-children" style="color: var(--gold); margin-right: 6px;"></i> កុមារ និងទារកសរុបទាំងអស់ (០-១៧ ឆ្នាំ)</strong></td>
        <td class="text-right"><strong style="color: var(--gold-light); font-size: 1.1rem;">${edu.total_children || 0}</strong> នាក់</td>
      </tr>
    `;
  }

  // Dropout Grades Breakdown Table
  const dropTbody = document.getElementById("table-dropouts-breakdown");
  if (dropTbody) {
    const grades = Object.entries(edu.dropout_breakdown || {});
    if (grades.length === 0) {
      dropTbody.innerHTML = `<tr><td colspan="2" class="text-center text-dim" style="padding: 1.5rem; text-align: center;">គ្មានទិន្នន័យបោះបង់ការសិក្សា</td></tr>`;
    } else {
      dropTbody.innerHTML = grades.map(([gr, cnt]) => `
        <tr>
          <td><span class="badge-tag dropout">${gr}</span></td>
          <td class="text-right"><strong>${cnt}</strong> នាក់</td>
        </tr>
      `).join("");
    }
  }
}

// --- Dynamic Member Form Cards (Mobile Optimized) ---
let memberRowCount = 0;

function addMemberRow(initialData = {}) {
  memberRowCount++;
  const container = document.getElementById("form-members-container");
  if (!container) return;

  const cardId = `member-card-${memberRowCount}`;
  const card = document.createElement("div");
  card.className = "member-entry-card";
  card.id = cardId;

  const isFirst = container.children.length === 0;
  const defaultRelation = initialData.relation || (isFirst ? "HEAD" : "CHILD");
  const defaultEdu = initialData.education_status || "PRIMARY";
  const defaultDropout = initialData.dropout_status || "ACTIVE";
  const birthCertVal = (initialData.birth_cert !== undefined && initialData.birth_cert !== null) ? String(initialData.birth_cert).replace(/[^0-9]/g, "") || "0" : "0";

  card.innerHTML = `
    <div class="member-card-header">
      <div class="member-card-header-left">
        <span class="member-num-pill">
          <i class="fa-solid fa-user"></i> សមាជិកទី <span class="member-index-num">${container.children.length + 1}</span>
        </span>
        <span class="member-age-pill">
          <i class="fa-solid fa-cake-candles"></i> អាយុ៖ <strong class="member-age-badge">${initialData.age || 0}</strong> ឆ្នាំ
        </span>
      </div>
      <button type="button" class="btn btn-sm btn-danger btn-remove-member" title="លុបសមាជិក">
        <i class="fa-solid fa-trash"></i> លុប
      </button>
    </div>

    <div class="member-card-fields">
      <div class="member-card-field-group">
        <label>គោត្តនាម-នាម *</label>
        <input type="text" class="form-input member-name" placeholder="ឧ. សុខ ចាន់ដារ៉ា" value="${initialData.full_name || ''}" required style="width: 100%;" />
      </div>

      <div class="member-card-field-group">
        <label>ភេទ *</label>
        <select class="form-select member-gender" style="width: 100%;">
          <option value="MALE" ${initialData.gender === 'MALE' ? 'selected' : ''}>ប្រុស (Male)</option>
          <option value="FEMALE" ${initialData.gender === 'FEMALE' ? 'selected' : ''}>ស្រី (Female)</option>
        </select>
      </div>

      <div class="member-card-field-group">
        <label>ថ្ងៃខែឆ្នាំកំណើត *</label>
        <input type="date" class="form-input member-dob" value="${initialData.dob || ''}" required style="width: 100%;" />
      </div>

      <div class="member-card-field-group">
        <label>ឋានៈក្នុងគ្រួសារ *</label>
        <select class="form-select member-relation" style="width: 100%;">
          <option value="HEAD" ${defaultRelation === 'HEAD' ? 'selected' : ''}>មេគ្រួសារ</option>
          <option value="SPOUSE" ${defaultRelation === 'SPOUSE' ? 'selected' : ''}>ប្រពន្ធ/ប្តី</option>
          <option value="CHILD" ${defaultRelation === 'CHILD' ? 'selected' : ''}>កូន</option>
          <option value="PARENT" ${defaultRelation === 'PARENT' ? 'selected' : ''}>ឪពុក/ម្តាយ</option>
          <option value="RELATIVE" ${defaultRelation === 'RELATIVE' ? 'selected' : ''}>សាច់ញាតិ</option>
          <option value="OTHER" ${defaultRelation === 'OTHER' ? 'selected' : ''}>ផ្សេងៗ</option>
        </select>
      </div>

      <div class="member-card-field-group">
        <label>កម្រិតវប្បធម៌</label>
        <select class="form-select member-edu" style="width: 100%;">
          <option value="NONE" ${defaultEdu === 'NONE' ? 'selected' : ''}>មិនបានរៀន</option>
          <option value="PRIMARY" ${defaultEdu === 'PRIMARY' ? 'selected' : ''}>ចូលរៀនបឋម</option>
          <option value="SECONDARY" ${defaultEdu === 'SECONDARY' ? 'selected' : ''}>ចូលរៀនមធ្យម</option>
          <option value="HIGHER" ${defaultEdu === 'HIGHER' ? 'selected' : ''}>ឧត្តមសិក្សា</option>
        </select>
      </div>

      <div class="member-card-field-group">
        <label>ស្ថានភាពសិក្សា និងកម្រិតថ្នាក់</label>
        <select class="form-select member-dropout" style="width: 100%;">
          <option value="ACTIVE" ${defaultDropout === 'ACTIVE' ? 'selected' : ''}>កំពុងរៀន</option>
          <option value="DROPOUT" ${defaultDropout === 'DROPOUT' ? 'selected' : ''}>បោះបង់ការសិក្សា</option>
        </select>
        <input type="text" class="form-input member-dropout-grade" 
          placeholder="${defaultDropout === 'DROPOUT' ? 'ថ្នាក់បោះបង់ (លេខឡាតាំង ឧ. 7)' : 'ថ្នាក់កំពុងរៀន (លេខឡាតាំង ឧ. 5)'}" 
          value="${initialData.dropout_grade || ''}" 
          inputmode="numeric" pattern="[0-9]*" title="សូមបញ្ចូលតែលេខឡាតាំងប៉ុណ្ណោះ (0-9)"
          style="margin-top: 0.35rem; width: 100%; font-size: 0.8rem; font-family: monospace; font-weight: 600;" />
        <small class="text-dim" style="font-size: 0.72rem;">* បញ្ចូលតែលេខឡាតាំង (0-9) ឧ. 7, 8, 9...</small>
      </div>

      <div class="member-card-field-group">
        <label>មុខរបរ</label>
        <input type="text" class="form-input member-occupation" placeholder="ឧ. កសិករ, សិស្ស..." value="${initialData.occupation || ''}" style="width: 100%;" />
      </div>

      <div class="member-card-field-group">
        <label>លេខសំបុត្រកំណើត (Birth Cert No.) *</label>
        <input type="text" class="form-input member-birthcert" value="${birthCertVal}" placeholder="0" inputmode="numeric" pattern="[0-9]*" title="សូមបញ្ចូលតែលេខឡាតាំងប៉ុណ្ណោះ (0-9)" style="width: 100%; font-family: monospace; font-weight: 600;" />
        <small class="text-dim" style="font-size: 0.72rem;">* លេខឡាតាំងប៉ុណ្ណោះ (0-9) លំនាំដើម៖ 0</small>
      </div>
    </div>
  `;

  container.appendChild(card);
  updateMemberIndices();

  // Grade input constraint: Latin digits only
  const gradeInput = card.querySelector(".member-dropout-grade");
  if (gradeInput) {
    gradeInput.addEventListener("input", (e) => {
      e.target.value = e.target.value.replace(/[^0-9]/g, "");
    });
  }

  // Birth Certificate input constraint: Latin digits only, default 0
  const bcInput = card.querySelector(".member-birthcert");
  if (bcInput) {
    bcInput.addEventListener("input", (e) => {
      e.target.value = e.target.value.replace(/[^0-9]/g, "");
    });
    bcInput.addEventListener("blur", (e) => {
      if (!e.target.value.trim()) e.target.value = "0";
    });
  }

  // Setup Real-time DOB -> Age calculation listener
  const dobInput = card.querySelector(".member-dob");
  const ageBadge = card.querySelector(".member-age-badge");
  const updateAge = () => {
    const calculatedAge = calculateAgeFromDob(dobInput.value);
    ageBadge.textContent = calculatedAge;
  };
  dobInput.addEventListener("change", updateAge);
  dobInput.addEventListener("input", updateAge);
  if (initialData.dob) updateAge();

  // Dynamic Grade placeholder based on School Attendance
  const dropSelect = card.querySelector(".member-dropout");
  dropSelect.addEventListener("change", (e) => {
    if (e.target.value === "DROPOUT") {
      gradeInput.placeholder = "ថ្នាក់បោះបង់ (លេខឡាតាំង ឧ. 7)";
    } else {
      gradeInput.placeholder = "ថ្នាក់កំពុងរៀន (លេខឡាតាំង ឧ. 5)";
    }
  });

  // Remove row listener
  card.querySelector(".btn-remove-member").addEventListener("click", () => {
    if (container.children.length > 1) {
      card.remove();
      updateMemberIndices();
    } else {
      window.showToast("គ្រួសារត្រូវតែមានសមាជិកយ៉ាងហោចណាស់ម្នាក់", "error");
    }
  });
}

function updateMemberIndices() {
  const container = document.getElementById("form-members-container");
  if (!container) return;
  Array.from(container.children).forEach((card, idx) => {
    const numEl = card.querySelector(".member-index-num");
    if (numEl) numEl.textContent = idx + 1;
  });
}

// --- Submit Family Registration Form ---
async function handleFamilyFormSubmit(e) {
  e.preventDefault();
  const villSelect = document.getElementById("form-village");
  let villageId = parseInt(villSelect?.value);

  // If villageId is missing or single village environment, fall back to first village in tree
  if (!villageId && state.geoTree.length > 0) {
    const firstProv = state.geoTree[0];
    if (firstProv.districts.length > 0 && firstProv.districts[0].communes.length > 0 && firstProv.districts[0].communes[0].villages.length > 0) {
      villageId = firstProv.districts[0].communes[0].villages[0].id;
    }
  }

  if (!villageId) {
    window.showToast("សូមជ្រើសរើសភូមិជាមុនសិន", "error");
    return;
  }

  const poorCategory = document.querySelector('input[name="form-poor"]:checked')?.value || "GENERAL";
  const addressNote = document.getElementById("form-address-note")?.value || "";

  // Collect members from dynamic cards
  const container = document.getElementById("form-members-container");
  const cards = container ? container.querySelectorAll(".member-entry-card") : [];
  if (cards.length === 0) {
    window.showToast("សូមបន្ថែមសមាជិកគ្រួសារយ៉ាងហោចណាស់ម្នាក់", "error");
    return;
  }

  const members = [];
  for (const card of cards) {
    const fullName = card.querySelector(".member-name")?.value.trim();
    const dob = card.querySelector(".member-dob")?.value;
    if (!fullName || !dob) {
      window.showToast("សូមបំពេញឈ្មោះ និងថ្ងៃខែឆ្នាំកំណើតឱ្យបានគ្រប់គ្រាន់", "error");
      return;
    }

    const gender = card.querySelector(".member-gender")?.value || "MALE";
    const relation = card.querySelector(".member-relation")?.value || "CHILD";
    const edu = card.querySelector(".member-edu")?.value || "PRIMARY";
    const dropout = card.querySelector(".member-dropout")?.value || "ACTIVE";
    const rawGrade = card.querySelector(".member-dropout-grade")?.value || "";
    const dropoutGrade = rawGrade.replace(/[^0-9]/g, "").trim();
    const rawBc = card.querySelector(".member-birthcert")?.value || "0";
    const birthCert = rawBc.replace(/[^0-9]/g, "") || "0";
    const occ = card.querySelector(".member-occupation")?.value || "";

    members.push({
      full_name: fullName,
      gender: gender,
      nationality: "ខ្មែរ",
      dob: dob,
      relation: relation,
      education_status: edu,
      dropout_status: dropout,
      dropout_grade: dropoutGrade ? dropoutGrade : null,
      birth_cert: birthCert,
      disability: "គ្មាន",
      occupation: occ,
      current_address: addressNote
    });
  }

  const payload = {
    village_id: villageId,
    poor_category: poorCategory,
    address_note: addressNote,
    status: "APPROVED",
    members: members
  };

  const submitBtn = document.getElementById("btn-submit-family");
  if (submitBtn) {
    submitBtn.disabled = true;
    submitBtn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> កំពុងរក្សាទុក...`;
  }

  try {
    if (navigator.onLine) {
      const res = await apiRequest("/api/families", {
        method: "POST",
        body: JSON.stringify(payload)
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "បរាជ័យក្នុងការចុះឈ្មោះគ្រួសារ");
      }
      const data = await res.json();
      window.showToast(`បានចុះបញ្ជីគ្រួសារជោគជ័យ! លេខកូដ៖ ${data.family_code}`, "success");
    } else {
      // Offline mode: save into IndexedDB queue
      await window.censusDB.savePendingFamily(payload);
      await window.syncManager.updateUI();
      window.showToast("រក្សាទុកក្នុងឧបករណ៍ (Offline) រួចរាល់! នឹង Sync ស្វ័យប្រវត្តិកាលណាមានអ៊ីនធឺណិត", "info");
    }

    // Reset Form & Close Modal
    resetRegistrationForm();
    window.closeRegistrationModal();
    switchTab("families");
    loadFamiliesList();
  } catch (err) {
    console.error("Save error:", err);
    window.showToast(err.message || "មានបញ្ហាក្នុងការរក្សាទុក", "error");
  } finally {
    if (submitBtn) {
      submitBtn.disabled = false;
      submitBtn.innerHTML = `<i class="fa-solid fa-floppy-disk"></i> រក្សាទុកគ្រួសារ និងសមាជិក`;
    }
  }
}

function resetRegistrationForm() {
  const container = document.getElementById("form-members-container");
  if (container) container.innerHTML = "";
  const addrEl = document.getElementById("form-address-note");
  if (addrEl) addrEl.value = "";
  memberRowCount = 0;
  // Add initial Head of Family card
  addMemberRow({ relation: "HEAD" });
  updatePreviewFamilyCode();
}

// --- Family Directory & Table View ---
async function loadFamiliesList() {
  const tbody = document.getElementById("families-table-tbody");
  if (!tbody) return;
  tbody.innerHTML = `<tr><td colspan="8" class="text-center text-dim" style="padding: 2.5rem; text-align: center;"><i class="fa-solid fa-spinner fa-spin" style="font-size: 1.5rem; display: block; margin-bottom: 0.5rem; color: #60a5fa;"></i> កំពុងផ្ទុកទិន្នន័យ...</td></tr>`;

  try {
    const poorFilter = document.getElementById("filter-list-poor")?.value || "";
    const statusFilter = document.getElementById("filter-list-status")?.value || "";
    const searchVal = document.getElementById("filter-list-search")?.value || "";

    const params = new URLSearchParams();
    if (poorFilter) params.append("poor_category", poorFilter);
    if (statusFilter) params.append("status_filter", statusFilter);
    if (searchVal) params.append("search", searchVal);
    params.append("limit", "1000");

    let families = [];
    if (navigator.onLine) {
      const res = await apiRequest(`/api/families?${params.toString()}`);
      if (res.ok) families = await res.json();
    }

    // Also include pending offline families if any
    const pending = await window.censusDB.getPendingFamilies();
    const offlineMapped = pending.map((f, idx) => ({
      id: "offline_" + idx,
      family_code: "ក្រៅបណ្តាញ (រង់ចាំ Sync)",
      head_name: f.members[0]?.full_name || "គ្មានឈ្មោះ",
      poor_category: f.poor_category,
      village_name_kh: "កត់ត្រាក្រៅបណ្តាញ",
      members_count: f.members.length,
      status: "PENDING_REVIEW",
      is_offline: true,
      raw_data: f
    }));

    const allFamilies = [...offlineMapped, ...families];
    state.familiesList = allFamilies;
    renderFamiliesTable(allFamilies);
  } catch (err) {
    console.error("Failed to load families:", err);
    tbody.innerHTML = `<tr><td colspan="8" class="text-center text-dim" style="padding: 2.5rem; text-align: center;"><i class="fa-solid fa-triangle-exclamation" style="font-size: 1.5rem; display: block; margin-bottom: 0.5rem; color: #f59e0b;"></i>មិនអាចទាញទិន្នន័យបានទេ</td></tr>`;
  }
}

function renderFamiliesTable(families) {
  const tbody = document.getElementById("families-table-tbody");
  const paginationContainer = document.getElementById("families-pagination-container");
  if (!tbody) return;

  const total = families.length;
  const pageSize = state.familiesPageSize || 15;
  const totalPages = Math.ceil(total / pageSize) || 1;

  if (state.familiesCurrentPage > totalPages) state.familiesCurrentPage = totalPages;
  if (state.familiesCurrentPage < 1) state.familiesCurrentPage = 1;

  if (total === 0) {
    tbody.innerHTML = `<tr><td colspan="8" class="text-center text-dim" style="padding: 3rem 1.5rem; text-align: center;"><i class="fa-regular fa-folder-open" style="font-size: 2rem; display: block; margin-bottom: 0.75rem; opacity: 0.4;"></i>មិនមានទិន្នន័យគ្រួសារដែលស្វែងរកទេ</td></tr>`;
    if (paginationContainer) paginationContainer.innerHTML = "";
    return;
  }

  const startIdx = (state.familiesCurrentPage - 1) * pageSize;
  const endIdx = Math.min(startIdx + pageSize, total);
  const pageItems = families.slice(startIdx, endIdx);

  const poorBadgeMap = {
    "IDPOOR_1": `<span class="badge-tag poor1">ក្រ១ (IDPoor 1)</span>`,
    "IDPOOR_2": `<span class="badge-tag poor2">ក្រ២ (IDPoor 2)</span>`,
    "GENERAL": `<span class="badge-tag general">ទូទៅ</span>`
  };

  const statusBadgeMap = {
    "APPROVED": `<span class="badge-tag approved"><i class="fa-solid fa-check"></i> បានអនុម័ត</span>`,
    "PENDING_REVIEW": `<span class="badge-tag pending"><i class="fa-solid fa-clock"></i> រង់ចាំពិនិត្យ</span>`,
    "REJECTED": `<span class="badge-tag dropout"><i class="fa-solid fa-xmark"></i> បដិសេធ</span>`
  };

  tbody.innerHTML = pageItems.map((f, index) => `
    <tr>
      <td class="text-center">${startIdx + index + 1}</td>
      <td>
        <strong style="color: #60a5fa;">${f.family_code}</strong>
        ${f.is_offline ? `<span class="badge-tag poor2" style="font-size: 0.65rem; margin-left: 4px;">Offline</span>` : ''}
      </td>
      <td><strong>${f.head_name || 'គ្មាន'}</strong></td>
      <td>${poorBadgeMap[f.poor_category] || f.poor_category}</td>
      <td>${f.village_name_kh || '-'}</td>
      <td class="text-center"><strong>${f.members_count || 0}</strong> នាក់</td>
      <td>${statusBadgeMap[f.status] || f.status}</td>
      <td class="text-center">
        <div style="display: inline-flex; gap: 0.4rem;">
          <button class="btn btn-sm btn-outline btn-view-family" data-id="${f.id}" title="ពិនិត្យមើលលម្អិត">
            <i class="fa-solid fa-eye"></i> មើល
          </button>
          ${(!f.is_offline && (state.currentUser?.role === 'ADMIN' || state.currentUser?.role === 'REVIEWER')) ? `
            <button class="btn btn-sm btn-success btn-approve-family" data-id="${f.id}" title="អនុម័ត">
              <i class="fa-solid fa-check-double"></i>
            </button>
          ` : ''}
          ${(!f.is_offline && state.currentUser?.role === 'ADMIN') ? `
            <button class="btn btn-sm btn-danger btn-delete-family" data-id="${f.id}" title="លុប">
              <i class="fa-solid fa-trash"></i>
            </button>
          ` : ''}
        </div>
      </td>
    </tr>
  `).join("");

  // Attach action listeners
  tbody.querySelectorAll(".btn-view-family").forEach(btn => {
    btn.addEventListener("click", () => openFamilyDetailModal(btn.getAttribute("data-id")));
  });

  tbody.querySelectorAll(".btn-approve-family").forEach(btn => {
    btn.addEventListener("click", () => approveFamily(btn.getAttribute("data-id")));
  });

  tbody.querySelectorAll(".btn-delete-family").forEach(btn => {
    btn.addEventListener("click", () => deleteFamily(btn.getAttribute("data-id")));
  });

  renderFamiliesPagination(total, totalPages, startIdx, endIdx);
}

function renderFamiliesPagination(total, totalPages, startIdx, endIdx) {
  const container = document.getElementById("families-pagination-container");
  if (!container) return;

  if (total <= 0) {
    container.innerHTML = "";
    return;
  }

  const currentPage = state.familiesCurrentPage;

  // Build page numbers list
  const pages = [];
  if (totalPages <= 7) {
    for (let i = 1; i <= totalPages; i++) pages.push(i);
  } else {
    pages.push(1);
    if (currentPage > 3) pages.push("...");
    const start = Math.max(2, currentPage - 1);
    const end = Math.min(totalPages - 1, currentPage + 1);
    for (let i = start; i <= end; i++) {
      if (!pages.includes(i)) pages.push(i);
    }
    if (currentPage < totalPages - 2) pages.push("...");
    if (!pages.includes(totalPages)) pages.push(totalPages);
  }

  container.innerHTML = `
    <div class="pagination-info">
      បង្ហាញ <strong style="color: #60a5fa;">${startIdx + 1} - ${endIdx}</strong> នៃ <strong style="color: var(--gold-light);">${total}</strong> គ្រួសារសរុប <span class="badge-tag general" style="margin-left: 6px; font-size: 0.72rem; padding: 2px 7px;">១៥ ក្នុង ១ ទំព័រ</span>
    </div>

    <div class="pagination-controls">
      <button type="button" class="pagination-btn btn-prev-page" ${currentPage <= 1 ? 'disabled' : ''} title="ទំព័រមុន">
        <i class="fa-solid fa-chevron-left"></i> មុន
      </button>

      ${pages.map(p => {
        if (p === "...") {
          return `<span class="pagination-ellipsis">...</span>`;
        }
        return `
          <button type="button" class="pagination-btn ${p === currentPage ? 'active' : ''} btn-page-num" data-page="${p}">
            ${p}
          </button>
        `;
      }).join("")}

      <button type="button" class="pagination-btn btn-next-page" ${currentPage >= totalPages ? 'disabled' : ''} title="ទំព័របន្ទាប់">
        បន្ទាប់ <i class="fa-solid fa-chevron-right"></i>
      </button>
    </div>
  `;

  // Attach event listeners
  container.querySelector(".btn-prev-page")?.addEventListener("click", () => {
    if (state.familiesCurrentPage > 1) {
      state.familiesCurrentPage--;
      renderFamiliesTable(state.familiesList);
      document.getElementById("view-families")?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  });

  container.querySelector(".btn-next-page")?.addEventListener("click", () => {
    if (state.familiesCurrentPage < totalPages) {
      state.familiesCurrentPage++;
      renderFamiliesTable(state.familiesList);
      document.getElementById("view-families")?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  });

  container.querySelectorAll(".btn-page-num").forEach(btn => {
    btn.addEventListener("click", () => {
      const page = parseInt(btn.getAttribute("data-page"));
      if (page && page !== state.familiesCurrentPage) {
        state.familiesCurrentPage = page;
        renderFamiliesTable(state.familiesList);
        document.getElementById("view-families")?.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    });
  });
}

// --- Family Detail Modal ---
async function openFamilyDetailModal(familyId) {
  const modal = document.getElementById("family-detail-modal");
  const modalContent = document.getElementById("family-detail-content");
  if (!modal || !modalContent) return;

  modalContent.innerHTML = `<div class="text-center" style="padding: 3rem;"><i class="fa-solid fa-spinner fa-spin"></i> កំពុងផ្ទុកព័ត៌មានគ្រួសារ...</div>`;
  modal.classList.add("active");

  try {
    let fam;
    if (String(familyId).startsWith("offline_")) {
      const idx = parseInt(familyId.replace("offline_", ""));
      const offlineList = await window.censusDB.getPendingFamilies();
      fam = offlineList[idx];
      fam.head_name = fam.members[0]?.full_name;
      fam.family_code = "ក្រៅបណ្តាញ (Pending Sync)";
    } else {
      const res = await apiRequest(`/api/families/${familyId}`);
      if (!res.ok) throw new Error("Could not fetch family");
      fam = await res.json();
    }

    const relationMap = {
      "HEAD": "មេគ្រួសារ", "SPOUSE": "ប្រពន្ធ/ប្តី", "CHILD": "កូន",
      "PARENT": "ឪពុក/ម្តាយ", "RELATIVE": "សាច់ញាតិ", "OTHER": "ផ្សេងៗ"
    };
    const eduMap = {
      "NONE": "មិនបានរៀន", "PRIMARY": "បឋមសិក្សា", "SECONDARY": "មធ្យមសិក្សា", "HIGHER": "ឧត្តមសិក្សា"
    };

    const poorBadgeMap = {
      "IDPOOR_1": `<span class="badge-tag poor1">ក្រ១ (IDPoor 1)</span>`,
      "IDPOOR_2": `<span class="badge-tag poor2">ក្រ២ (IDPoor 2)</span>`,
      "GENERAL": `<span class="badge-tag general">ទូទៅ</span>`
    };

    modalContent.innerHTML = `
      <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem; margin-bottom: 1.5rem; background: var(--bg-surface); padding: 1.25rem; border-radius: var(--radius-md); border: 1px solid var(--border-color);">
        <div><span class="text-dim">លេខកូដគ្រួសារ៖</span> <br/><strong style="font-size: 1.1rem; color: #60a5fa;">${fam.family_code}</strong></div>
        <div><span class="text-dim">ប្រភេទគ្រួសារ៖</span> <br/><strong>${poorBadgeMap[fam.poor_category] || fam.poor_category}</strong></div>
        <div><span class="text-dim">ទីតាំងរដ្ឋបាល៖</span> <br/><strong>ភូមិ ${fam.village_name_kh || '-'}, ឃុំ ${fam.commune_name_kh || '-'}</strong></div>
        <div><span class="text-dim">អាសយដ្ឋាន/ចំណាំ៖</span> <br/><strong>${fam.address_note || 'គ្មាន'}</strong></div>
        ${!fam.is_offline ? `
          <div style="grid-column: 1 / -1; display: flex; justify-content: flex-end; padding-top: 0.5rem; border-top: 1px dashed var(--border-color);">
            <button type="button" class="btn btn-sm btn-outline btn-open-edit-family" 
              data-family-id="${fam.id}" data-family-code="${fam.family_code}" data-poor="${fam.poor_category}" data-address="${(fam.address_note || '').replace(/"/g, '&quot;')}">
              <i class="fa-solid fa-pen-to-square"></i> កែសម្រួលព័ត៌មានគ្រួសារ
            </button>
          </div>
        ` : ''}
      </div>

      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.85rem; flex-wrap: wrap; gap: 0.5rem;">
        <h3 style="font-size: 1.05rem; margin: 0; color: var(--gold-light); display: flex; align-items: center; gap: 0.5rem;">
          <i class="fa-solid fa-users"></i> បញ្ជីសមាជិកគ្រួសារទាំងអស់ (${fam.members?.length || 0} នាក់)
        </h3>
        ${!fam.is_offline ? `
          <button type="button" class="btn btn-sm btn-gold btn-open-add-member" data-family-id="${fam.id}" data-family-code="${fam.family_code}">
            <i class="fa-solid fa-user-plus"></i> + បន្ថែមសមាជិក
          </button>
        ` : ''}
      </div>

      <div class="table-responsive">
        <table class="custom-table">
          <thead>
            <tr>
              <th>ល.រ</th>
              <th>គោត្តនាម-នាម</th>
              <th>ភេទ</th>
              <th>ថ្ងៃខែឆ្នាំកំណើត</th>
              <th>អាយុ</th>
              <th>ឋានៈ</th>
              <th>កម្រិតវប្បធម៌</th>
              <th>ស្ថានភាពសិក្សា</th>
              <th>សំបុត្រកំណើត</th>
              <th>មុខរបរ</th>
              <th style="text-align: center; min-width: 140px;">សកម្មភាព</th>
            </tr>
          </thead>
          <tbody>
            ${(fam.members || []).map((m, idx) => `
              <tr>
                <td class="text-center">${idx + 1}</td>
                <td><strong>${m.full_name}</strong></td>
                <td><span class="badge-tag ${m.gender === 'MALE' ? 'male' : 'female'}">${m.gender === 'MALE' ? 'ប្រុស' : 'ស្រី'}</span></td>
                <td>${m.dob}</td>
                <td class="text-center"><strong>${m.age}</strong> ឆ្នាំ</td>
                <td><span class="badge-tag general">${relationMap[m.relation] || m.relation}</span></td>
                <td>${eduMap[m.education_status] || m.education_status}</td>
                <td>
                  ${m.dropout_status === 'DROPOUT' ? 
                    `<span class="badge-tag dropout">បោះបង់ (${m.dropout_grade || 'មិនបញ្ជាក់'})</span>` : 
                    (m.dropout_grade ? `<span class="badge-tag approved">កំពុងរៀន (${m.dropout_grade})</span>` : `<span class="badge-tag approved">កំពុងរៀន</span>`)}
                </td>
                <td class="text-center">
                  <span class="badge-tag ${m.birth_cert && String(m.birth_cert).trim() !== '0' && String(m.birth_cert).trim() !== 'false' ? 'cert-yes' : 'cert-no'}">
                    ${m.birth_cert && String(m.birth_cert).trim() !== '0' && String(m.birth_cert).trim() !== 'false' ? m.birth_cert : '0 (គ្មាន)'}
                  </span>
                </td>
                <td>${m.occupation || '-'}</td>
                <td class="text-center">
                  ${!fam.is_offline ? `
                    <div style="display: inline-flex; gap: 0.4rem; justify-content: center; align-items: center;">
                      <button type="button" class="btn btn-sm btn-edit btn-edit-single-member" 
                        data-family-id="${fam.id}" data-family-code="${fam.family_code}" data-member-id="${m.id}" title="កែសម្រួលព័ត៌មានសមាជិក">
                        <i class="fa-solid fa-pen-to-square"></i> កែប្រែ
                      </button>
                      <button type="button" class="btn btn-sm btn-danger btn-delete-single-member" 
                        data-family-id="${fam.id}" data-member-id="${m.id}" data-name="${m.full_name}" title="លុបសមាជិក">
                        <i class="fa-solid fa-trash"></i>
                      </button>
                    </div>
                  ` : '-'}
                </td>
              </tr>
            `).join("")}
          </tbody>
        </table>
      </div>
    `;

    // Attach listener to Edit Family button
    modalContent.querySelectorAll(".btn-open-edit-family").forEach(btn => {
      btn.addEventListener("click", () => {
        const fId = btn.getAttribute("data-family-id");
        const fCode = btn.getAttribute("data-family-code");
        const fPoor = btn.getAttribute("data-poor");
        const fAddress = btn.getAttribute("data-address");
        openEditFamilyModal(fId, fCode, fPoor, fAddress);
      });
    });

    // Attach listener to + Add Member button
    modalContent.querySelectorAll(".btn-open-add-member").forEach(btn => {
      btn.addEventListener("click", () => {
        const fId = btn.getAttribute("data-family-id");
        const fCode = btn.getAttribute("data-family-code");
        openAddMemberModal(fId, fCode);
      });
    });

    // Attach listener to Edit Member buttons
    modalContent.querySelectorAll(".btn-edit-single-member").forEach(btn => {
      btn.addEventListener("click", () => {
        const fId = btn.getAttribute("data-family-id");
        const fCode = btn.getAttribute("data-family-code");
        const mId = btn.getAttribute("data-member-id");
        const mData = (fam.members || []).find(x => String(x.id) === String(mId));
        if (mData) {
          openEditMemberModal(fId, fCode, mData);
        } else {
          console.error("Could not find member data for id:", mId);
        }
      });
    });

    // Attach listener to Delete Member buttons
    modalContent.querySelectorAll(".btn-delete-single-member").forEach(btn => {
      btn.addEventListener("click", () => {
        const fId = btn.getAttribute("data-family-id");
        const mId = btn.getAttribute("data-member-id");
        const mName = btn.getAttribute("data-name");
        deleteSingleMember(fId, mId, mName);
      });
    });

  } catch (err) {
    modalContent.innerHTML = `<div class="text-center text-dim" style="padding: 2rem;">មានកំហុសក្នុងការទាញយកទិន្នន័យ</div>`;
  }
}

// --- Family Details Edit Modal Management ---
function openEditFamilyModal(familyId, familyCode, poorCategory, addressNote) {
  const modal = document.getElementById("edit-family-modal");
  if (!modal) return;

  document.getElementById("edit-family-id").value = familyId || "";
  document.getElementById("edit-family-code-display").textContent = familyCode || "-";
  document.getElementById("edit-family-poor").value = poorCategory || "GENERAL";
  document.getElementById("edit-family-address").value = addressNote || "";

  modal.classList.add("active");
}

async function handleEditFamilyFormSubmit(e) {
  e.preventDefault();
  const familyId = document.getElementById("edit-family-id")?.value;
  const poorCategory = document.getElementById("edit-family-poor")?.value;
  const addressNote = document.getElementById("edit-family-address")?.value.trim();

  if (!familyId) return;

  const btn = document.getElementById("btn-submit-edit-family");
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> កំពុងរក្សាទុក...`;
  }

  try {
    const res = await apiRequest(`/api/families/${familyId}`, {
      method: "PUT",
      body: JSON.stringify({
        poor_category: poorCategory,
        address_note: addressNote
      })
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "បរាជ័យក្នុងការកែប្រែព័ត៌មានគ្រួសារ");
    }

    window.showToast("បានកែប្រែព័ត៌មានគ្រួសារដោយជោគជ័យ!", "success");
    document.getElementById("edit-family-modal")?.classList.remove("active");

    // Refresh Family Details Modal and list
    openFamilyDetailModal(familyId);
    loadFamiliesList();
    loadDashboardStats();
  } catch (err) {
    console.error("Edit family error:", err);
    window.showToast(err.message || "មានបញ្ហាក្នុងការកែប្រែព័ត៌មានគ្រួសារ", "error");
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = `<i class="fa-solid fa-floppy-disk"></i> រក្សាទុកការកែប្រែ`;
    }
  }
}

// --- Single Member Management (Add / Edit / Delete) ---
function openAddMemberModal(familyId, familyCode) {
  const modal = document.getElementById("single-member-modal");
  if (!modal) return;

  document.getElementById("single-member-family-id").value = familyId;
  document.getElementById("single-member-id").value = "";
  document.getElementById("single-member-name").value = "";
  document.getElementById("single-member-gender").value = "MALE";
  document.getElementById("single-member-dob").value = "";
  document.getElementById("single-member-age-display").textContent = "0";
  document.getElementById("single-member-relation").value = "CHILD";
  document.getElementById("single-member-edu").value = "PRIMARY";
  document.getElementById("single-member-dropout").value = "ACTIVE";
  document.getElementById("single-member-grade").value = "";
  document.getElementById("single-member-grade").placeholder = "ថ្នាក់កំពុងរៀន (លេខឡាតាំង ឧ. 5)";
  document.getElementById("single-member-grade").style.display = "block";
  document.getElementById("single-member-occupation").value = "";
  document.getElementById("single-member-birthcert").value = "0";

  const iconEl = document.getElementById("single-member-modal-icon");
  if (iconEl) {
    iconEl.className = "fa-solid fa-user-plus";
  }

  const titleEl = document.getElementById("single-member-modal-title");
  if (titleEl) {
    titleEl.textContent = `បន្ថែមសមាជិកថ្មីចូលគ្រួសារ (${familyCode})`;
  }

  const submitBtn = document.getElementById("btn-submit-single-member");
  if (submitBtn) {
    submitBtn.innerHTML = `<i class="fa-solid fa-floppy-disk"></i> រក្សាទុកសមាជិក`;
  }

  modal.classList.add("active");
}

function openEditMemberModal(familyId, familyCode, member) {
  const modal = document.getElementById("single-member-modal");
  if (!modal) return;

  document.getElementById("single-member-family-id").value = familyId;
  document.getElementById("single-member-id").value = member.id;
  document.getElementById("single-member-name").value = member.full_name || "";
  document.getElementById("single-member-gender").value = member.gender || "MALE";
  document.getElementById("single-member-dob").value = member.dob || "";
  document.getElementById("single-member-age-display").textContent = member.age !== undefined && member.age !== null ? member.age : calculateAgeFromDob(member.dob);
  document.getElementById("single-member-relation").value = member.relation || "CHILD";
  document.getElementById("single-member-edu").value = member.education_status || "PRIMARY";
  document.getElementById("single-member-dropout").value = member.dropout_status || "ACTIVE";
  document.getElementById("single-member-grade").value = member.dropout_grade || "";
  document.getElementById("single-member-grade").placeholder = member.dropout_status === "DROPOUT" ? "ថ្នាក់បោះបង់ (លេខឡាតាំង ឧ. 7)" : "ថ្នាក់កំពុងរៀន (លេខឡាតាំង ឧ. 5)";
  document.getElementById("single-member-occupation").value = member.occupation || "";
  document.getElementById("single-member-birthcert").value = member.birth_cert || "0";

  const iconEl = document.getElementById("single-member-modal-icon");
  if (iconEl) {
    iconEl.className = "fa-solid fa-user-pen";
  }

  const titleEl = document.getElementById("single-member-modal-title");
  if (titleEl) {
    titleEl.textContent = `កែសម្រួលព័ត៌មានសមាជិក៖ ${member.full_name} (${familyCode})`;
  }

  const submitBtn = document.getElementById("btn-submit-single-member");
  if (submitBtn) {
    submitBtn.innerHTML = `<i class="fa-solid fa-floppy-disk"></i> រក្សាទុកការកែប្រែ`;
  }

  modal.classList.add("active");
}

async function handleSingleMemberFormSubmit(e) {
  e.preventDefault();
  const familyId = document.getElementById("single-member-family-id")?.value;
  const memberId = document.getElementById("single-member-id")?.value;
  const fullName = document.getElementById("single-member-name")?.value.trim();
  const gender = document.getElementById("single-member-gender")?.value || "MALE";
  const dob = document.getElementById("single-member-dob")?.value;
  const relation = document.getElementById("single-member-relation")?.value || "CHILD";
  const edu = document.getElementById("single-member-edu")?.value || "PRIMARY";
  const dropout = document.getElementById("single-member-dropout")?.value || "ACTIVE";
  const rawGrade = document.getElementById("single-member-grade")?.value || "";
  const grade = rawGrade.replace(/[^0-9]/g, "").trim();
  const occupation = document.getElementById("single-member-occupation")?.value.trim() || "";
  const rawBc = document.getElementById("single-member-birthcert")?.value || "0";
  const birthCert = rawBc.replace(/[^0-9]/g, "") || "0";

  if (!familyId || !fullName || !dob) {
    window.showToast("សូមបំពេញឈ្មោះ និងថ្ងៃខែឆ្នាំកំណើតឱ្យបានត្រឹមត្រូវ", "error");
    return;
  }

  const payload = {
    full_name: fullName,
    gender: gender,
    nationality: "ខ្មែរ",
    dob: dob,
    relation: relation,
    education_status: edu,
    dropout_status: dropout,
    dropout_grade: grade ? grade : null,
    birth_cert: birthCert,
    disability: "គ្មាន",
    occupation: occupation,
    current_address: ""
  };

  const btn = document.getElementById("btn-submit-single-member");
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> កំពុងរក្សាទុក...`;
  }

  try {
    const url = memberId ? `/api/families/members/${memberId}` : `/api/families/${familyId}/members`;
    const method = memberId ? "PUT" : "POST";

    const res = await apiRequest(url, {
      method: method,
      body: JSON.stringify(payload)
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || (memberId ? "បរាជ័យក្នុងការកែប្រែសមាជិក" : "បរាជ័យក្នុងការបន្ថែមសមាជិក"));
    }

    const actionText = memberId ? "បានកែប្រែព័ត៌មានសមាជិក" : "បានបន្ថែមសមាជិក";
    window.showToast(`${actionText} "${fullName}" ដោយជោគជ័យ!`, "success");
    document.getElementById("single-member-modal")?.classList.remove("active");

    // Refresh Family Details Modal and list
    openFamilyDetailModal(familyId);
    loadFamiliesList();
    loadDashboardStats();
  } catch (err) {
    console.error("Member submit error:", err);
    window.showToast(err.message || "មានបញ្ហាក្នុងការរក្សាទុកសមាជិក", "error");
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = `<i class="fa-solid fa-floppy-disk"></i> រក្សាទុកសមាជិក`;
    }
  }
}

async function deleteSingleMember(familyId, memberId, memberName) {
  if (!confirm(`តើអ្នកពិតជាចង់លុបសមាជិក "${memberName}" ចេញពីគ្រួសារនេះមែនទេ? សកម្មភាពនេះមិនអាចត្រឡប់វិញបានឡើយ!`)) {
    return;
  }

  try {
    const res = await apiRequest(`/api/families/members/${memberId}`, {
      method: "DELETE"
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "បរាជ័យក្នុងការលុបសមាជិក");
    }

    window.showToast(`បានលុបសមាជិក "${memberName}" ដោយជោគជ័យ!`, "success");

    // Refresh detail modal and list
    openFamilyDetailModal(familyId);
    loadFamiliesList();
    loadDashboardStats();
  } catch (err) {
    console.error("Delete member error:", err);
    window.showToast(err.message || "មានបញ្ហាក្នុងការលុបសមាជិក", "error");
  }
}

async function approveFamily(id) {
  if (!confirm("តើអ្នកពិតជាចង់អនុម័ត (Approve) គ្រួសារនេះមែនទេ?")) return;
  try {
    const res = await apiRequest(`/api/families/${id}/status?new_status=APPROVED`, { method: "PATCH" });
    if (res.ok) {
      window.showToast("បានអនុម័តគ្រួសារដោយជោគជ័យ", "success");
      loadFamiliesList();
    }
  } catch (err) {
    window.showToast("បរាជ័យក្នុងការអនុម័ត", "error");
  }
}

async function deleteFamily(id) {
  if (!confirm("តើអ្នកពិតជាចង់លុបគ្រួសារ និងសមាជិកទាំងអស់នេះមែនទេ? សកម្មភាពនេះមិនអាចត្រឡប់វិញបានទេ!")) return;
  try {
    const res = await apiRequest(`/api/families/${id}`, { method: "DELETE" });
    if (res.ok) {
      window.showToast("បានលុបព័ត៌មានគ្រួសារដោយជោគជ័យ", "success");
      loadFamiliesList();
    }
  } catch (err) {
    window.showToast("បរាជ័យក្នុងការលុប", "error");
  }
}

// --- Geographic Hierarchy Explorer ---
function loadGeoExplorer() {
  const container = document.getElementById("geo-explorer-container");
  if (!container) return;

  if (state.geoTree.length === 0) {
    container.innerHTML = `<div class="text-center text-dim" style="padding: 2rem;">កំពុងផ្ទុកទិន្នន័យភូមិសាស្ត្រ...</div>`;
    return;
  }

  container.innerHTML = state.geoTree.map(p => `
    <div class="card card-hover" style="margin-bottom: 1.25rem;">
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.75rem;">
        <div>
          <strong style="font-size: 1.2rem; color: var(--gold-light);">${p.name_kh} (${p.name_en})</strong>
          <span class="badge-tag general" style="margin-left: 0.5rem;">កូដរដ្ឋបាល: <strong>${p.code}</strong></span>
        </div>
        <span class="text-dim" style="font-size: 0.85rem;">មាន ${p.districts.length} ស្រុក/ខណ្ឌ</span>
      </div>

      <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 1rem;">
        ${p.districts.map(d => `
          <div style="background: var(--bg-surface); padding: 1rem; border-radius: var(--radius-md); border: 1px solid var(--border-color);">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.65rem;">
              <strong style="color: #60a5fa; font-size: 1.02rem;">
                <i class="fa-solid fa-landmark" style="margin-right: 6px;"></i> ${d.name_kh} (${d.name_en})
              </strong>
              <span class="badge-tag poor2" style="font-size: 0.75rem;">កូដស្រុក: ${d.code}</span>
            </div>
            
            <div style="display: flex; flex-direction: column; gap: 0.75rem;">
              ${d.communes.map(c => `
                <div style="background: rgba(255,255,255,0.02); padding: 0.75rem; border-radius: var(--radius-sm); border: 1px dashed rgba(255,255,255,0.1);">
                  <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
                    <span style="font-weight: 700; color: #fff;">
                      <i class="fa-solid fa-map-pin" style="color: #38bdf8; margin-right: 5px;"></i> ${c.name_kh} (${c.name_en})
                    </span>
                    <span class="badge-tag general" style="font-size: 0.72rem;">កូដឃុំ: ${c.code}</span>
                  </div>
                  
                  <!-- Village Level List -->
                  <div style="margin-top: 0.4rem; display: flex; flex-direction: column; gap: 0.4rem;">
                    ${c.villages.map(v => `
                      <div style="background: rgba(245, 158, 11, 0.08); border-left: 3px solid var(--gold); padding: 0.5rem 0.75rem; border-radius: 4px; display: flex; justify-content: space-between; align-items: center;">
                        <span style="color: var(--gold-light); font-weight: 600; font-size: 0.92rem;">
                          <i class="fa-solid fa-house" style="color: var(--gold); margin-right: 6px;"></i> ${v.name_kh} (${v.name_en})
                        </span>
                        <span class="badge-tag approved" style="font-size: 0.72rem; font-family: monospace;">កូដភូមិ: ${v.code}</span>
                      </div>
                    `).join("")}
                  </div>
                </div>
              `).join("")}
            </div>
          </div>
        `).join("")}
      </div>
    </div>
  `).join("");
}

// --- User Management (Admin & Users) ---
let allUsersList = [];

async function loadUsersList() {
  const tbody = document.getElementById("users-table-tbody");
  if (!tbody) return;
  tbody.innerHTML = `<tr><td colspan="7" class="text-center text-dim" style="padding: 2rem; text-align: center;"><i class="fa-solid fa-spinner fa-spin" style="font-size: 1.4rem; display: block; margin-bottom: 0.5rem; color: #60a5fa;"></i> កំពុងផ្ទុកទិន្នន័យអ្នកប្រើប្រាស់...</td></tr>`;

  try {
    const res = await apiRequest("/api/auth/users");
    if (!res.ok) {
      if (res.status === 403) {
        tbody.innerHTML = `<tr><td colspan="7" class="text-center text-dim" style="padding: 2rem; text-align: center;"><i class="fa-solid fa-lock" style="font-size: 1.4rem; display: block; margin-bottom: 0.5rem; color: #f59e0b;"></i> ត្រូវការសិទ្ធិជា Admin ដើម្បីគ្រប់គ្រងអ្នកប្រើប្រាស់</td></tr>`;
        return;
      }
      throw new Error("Failed to load users");
    }
    allUsersList = await res.json();
    renderUsersTable();
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="7" class="text-center text-dim" style="padding: 2rem; text-align: center;">មិនអាចទាញយកទិន្នន័យអ្នកប្រើប្រាស់បានទេ</td></tr>`;
  }
}

function renderUsersTable() {
  const tbody = document.getElementById("users-table-tbody");
  if (!tbody) return;

  const search = (document.getElementById("filter-user-search")?.value || "").toLowerCase();
  const roleFilter = document.getElementById("filter-user-role")?.value || "";

  let filtered = allUsersList.filter(u => {
    const matchSearch = !search || (u.full_name || "").toLowerCase().includes(search) || (u.username || "").toLowerCase().includes(search);
    const matchRole = !roleFilter || u.role === roleFilter;
    return matchSearch && matchRole;
  });

  if (filtered.length === 0) {
    tbody.innerHTML = `<tr><td colspan="7" class="text-center text-dim" style="padding: 2.5rem; text-align: center;"><i class="fa-regular fa-user" style="font-size: 1.8rem; display: block; margin-bottom: 0.5rem; opacity: 0.4;"></i>គ្មានគណនីត្រូវនឹងលក្ខខណ្ឌស្វែងរកទេ</td></tr>`;
    return;
  }

  const roleBadgeMap = {
    "ADMIN": `<span class="role-tag admin">Admin ថ្នាក់លើ</span>`,
    "COLLECTOR": `<span class="role-tag collector">អ្នកស្រង់ទិន្នន័យ (User)</span>`
  };

  const levelMap = {
    "ALL": "ទូទាំងប្រទេស",
    "PROVINCE": "ថ្នាក់ខេត្ត/រាជធានី",
    "DISTRICT": "ថ្នាក់ស្រុក/ខណ្ឌ",
    "COMMUNE": "ថ្នាក់ឃុំ/សង្កាត់",
    "VILLAGE": "ថ្នាក់ភូមិ"
  };

  tbody.innerHTML = filtered.map((u, idx) => `
    <tr>
      <td class="text-center">${idx + 1}</td>
      <td><strong>${u.full_name}</strong></td>
      <td><code style="color: #60a5fa; background: rgba(37,99,235,0.1); padding: 2px 6px; border-radius: 4px;">${u.username}</code></td>
      <td>${roleBadgeMap[u.role] || u.role}</td>
      <td>
        <span>${levelMap[u.assigned_level] || u.assigned_level || 'ទូទៅ'}</span>
        ${u.assigned_geo_code ? `<span class="badge-tag general" style="font-size: 0.7rem; margin-left: 4px;">កូដ: ${u.assigned_geo_code}</span>` : ''}
      </td>
      <td class="text-center">
        ${u.is_active ? 
          `<span class="badge-tag approved"><i class="fa-solid fa-check"></i> សកម្ម</span>` : 
          `<span class="badge-tag dropout"><i class="fa-solid fa-ban"></i> ផ្អាក</span>`}
      </td>
      <td class="text-center">
        <div style="display: inline-flex; gap: 0.35rem;">
          <button type="button" class="btn btn-sm btn-outline btn-edit-user" data-id="${u.id}" title="កែប្រែព័ត៌មាន">
            <i class="fa-solid fa-pen-to-square"></i>
          </button>
          <button type="button" class="btn btn-sm ${u.is_active ? 'btn-outline' : 'btn-success'} btn-toggle-user-status" data-id="${u.id}" title="${u.is_active ? 'ផ្អាកគណនី' : 'បើកដំណើរការឡើងវិញ'}">
            <i class="fa-solid ${u.is_active ? 'fa-user-slash' : 'fa-user-check'}"></i>
          </button>
          <button type="button" class="btn btn-sm btn-danger btn-delete-user" data-id="${u.id}" title="លុបគណនី">
            <i class="fa-solid fa-trash"></i>
          </button>
        </div>
      </td>
    </tr>
  `).join("");

  // Action listeners
  tbody.querySelectorAll(".btn-edit-user").forEach(btn => {
    btn.addEventListener("click", () => openEditUserModal(parseInt(btn.getAttribute("data-id"))));
  });

  tbody.querySelectorAll(".btn-toggle-user-status").forEach(btn => {
    btn.addEventListener("click", () => toggleUserStatus(parseInt(btn.getAttribute("data-id"))));
  });

  tbody.querySelectorAll(".btn-delete-user").forEach(btn => {
    btn.addEventListener("click", () => deleteUser(parseInt(btn.getAttribute("data-id"))));
  });
}

function openCreateUserModal() {
  document.getElementById("manage-user-id").value = "";
  document.getElementById("user-modal-title").innerHTML = `<i class="fa-solid fa-user-plus" style="color: var(--gold-light); margin-right: 6px;"></i> បង្កើតគណនីអ្នកប្រើប្រាស់ថ្មី`;
  document.getElementById("manage-user-fullname").value = "";
  document.getElementById("manage-user-username").value = "";
  document.getElementById("manage-user-username").disabled = false;
  document.getElementById("manage-user-password").value = "";
  document.getElementById("manage-user-password").required = true;
  document.getElementById("label-user-password").textContent = "ពាក្យសម្ងាត់ (Password) *";
  document.getElementById("hint-user-password").style.display = "none";
  document.getElementById("manage-user-role").value = "COLLECTOR";
  document.getElementById("manage-user-level").value = "VILLAGE";
  document.getElementById("manage-user-geocode").value = "";

  document.getElementById("user-modal")?.classList.add("active");
}

function openEditUserModal(userId) {
  const user = allUsersList.find(u => u.id === userId);
  if (!user) return;

  document.getElementById("manage-user-id").value = user.id;
  document.getElementById("user-modal-title").innerHTML = `<i class="fa-solid fa-user-pen" style="color: var(--gold-light); margin-right: 6px;"></i> កែប្រែព័ត៌មានគណនី (${user.username})`;
  document.getElementById("manage-user-fullname").value = user.full_name;
  document.getElementById("manage-user-username").value = user.username;
  document.getElementById("manage-user-username").disabled = true;
  document.getElementById("manage-user-password").value = "";
  document.getElementById("manage-user-password").required = false;
  document.getElementById("label-user-password").textContent = "ពាក្យសម្ងាត់ថ្មី (បើមិនប្តូរ ទុកទទេ)";
  document.getElementById("hint-user-password").style.display = "block";
  document.getElementById("manage-user-role").value = user.role;
  document.getElementById("manage-user-level").value = user.assigned_level || "ALL";
  document.getElementById("manage-user-geocode").value = user.assigned_geo_code || "";

  document.getElementById("user-modal")?.classList.add("active");
}

async function handleUserFormSubmit(e) {
  e.preventDefault();
  const userId = document.getElementById("manage-user-id").value;
  const fullName = document.getElementById("manage-user-fullname").value.trim();
  const username = document.getElementById("manage-user-username").value.trim();
  const password = document.getElementById("manage-user-password").value;
  const role = document.getElementById("manage-user-role").value;
  const level = document.getElementById("manage-user-level").value;
  const geoCode = document.getElementById("manage-user-geocode").value.trim() || null;

  const saveBtn = document.getElementById("btn-save-user");
  saveBtn.disabled = true;

  try {
    if (!userId) {
      // Create new user
      const payload = {
        full_name: fullName,
        username: username,
        password: password,
        role: role,
        assigned_level: level,
        assigned_geo_code: geoCode
      };
      const res = await apiRequest("/api/auth/users", {
        method: "POST",
        body: JSON.stringify(payload)
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "បរាជ័យក្នុងការបង្កើតគណនី");
      }
      window.showToast("បានបង្កើតគណនីអ្នកប្រើប្រាស់ថ្មីដោយជោគជ័យ", "success");
    } else {
      // Update existing user
      const payload = {
        full_name: fullName,
        role: role,
        assigned_level: level,
        assigned_geo_code: geoCode
      };
      if (password) payload.password = password;

      const res = await apiRequest(`/api/auth/users/${userId}`, {
        method: "PUT",
        body: JSON.stringify(payload)
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "បរាជ័យក្នុងការកែប្រែគណនី");
      }
      window.showToast("បានកែប្រែព័ត៌មានគណនីដោយជោគជ័យ", "success");
    }

    document.getElementById("user-modal")?.classList.remove("active");
    loadUsersList();
  } catch (err) {
    window.showToast(err.message, "error");
  } finally {
    saveBtn.disabled = false;
  }
}

async function toggleUserStatus(userId) {
  try {
    const res = await apiRequest(`/api/auth/users/${userId}/toggle-status`, { method: "PATCH" });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "បរាជ័យក្នុងការផ្លាស់ប្តូរស្ថានភាព");
    }
    const updated = await res.json();
    window.showToast(`គណនី ${updated.username} ត្រូវបាន ${updated.is_active ? 'បើកដំណើរការ' : 'ផ្អាក'}`, "success");
    loadUsersList();
  } catch (err) {
    window.showToast(err.message, "error");
  }
}

async function deleteUser(userId) {
  if (!confirm("តើអ្នកពិតជាចង់លុបគណនីនេះមែនទេ? សកម្មភាពនេះមិនអាចត្រឡប់វិញបានទេ!")) return;
  try {
    const res = await apiRequest(`/api/auth/users/${userId}`, { method: "DELETE" });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "បរាជ័យក្នុងការលុបគណនី");
    }
    window.showToast("បានលុបគណនីដោយជោគជ័យ", "success");
    loadUsersList();
  } catch (err) {
    window.showToast(err.message, "error");
  }
}

// --- User Access Audit Logs ---
let allAuditLogs = [];

async function loadUserLogs() {
  const tbody = document.getElementById("logs-table-tbody");
  if (!tbody) return;
  tbody.innerHTML = `<tr><td colspan="8" class="text-center text-dim" style="padding: 2rem; text-align: center;"><i class="fa-solid fa-spinner fa-spin" style="font-size: 1.4rem; display: block; margin-bottom: 0.5rem; color: #60a5fa;"></i> កំពុងទាញយកកំណត់ហេតុ...</td></tr>`;

  try {
    const res = await apiRequest("/api/auth/logs?limit=200");
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "បរាជ័យក្នុងការទាញយកកំណត់ហេតុ");
    }
    allAuditLogs = await res.json();
    renderLogsTable();
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="8" class="text-center text-dim" style="padding: 2rem; text-align: center; color: #ef4444;">កំហុស៖ ${err.message}</td></tr>`;
  }
}

function renderLogsTable() {
  const tbody = document.getElementById("logs-table-tbody");
  if (!tbody) return;

  const search = document.getElementById("filter-log-search")?.value.toLowerCase().trim() || "";
  const actionFilter = document.getElementById("filter-log-action")?.value || "";

  let filtered = allAuditLogs.filter(log => {
    const matchSearch = !search || 
      (log.username || "").toLowerCase().includes(search) || 
      (log.full_name || "").toLowerCase().includes(search) ||
      (log.ip_address || "").toLowerCase().includes(search);
    const matchAction = !actionFilter || log.action === actionFilter;
    return matchSearch && matchAction;
  });

  if (filtered.length === 0) {
    tbody.innerHTML = `<tr><td colspan="8" class="text-center text-dim" style="padding: 2.5rem; text-align: center;"><i class="fa-regular fa-clock" style="font-size: 1.8rem; display: block; margin-bottom: 0.5rem; opacity: 0.4;"></i>គ្មានកំណត់ហេតុត្រូវនឹងលក្ខខណ្ឌស្វែងរកទេ</td></tr>`;
    return;
  }

  const actionBadgeMap = {
    "LOGIN_SUCCESS": `<span class="badge-tag approved" style="font-size: 0.76rem;"><i class="fa-solid fa-circle-check"></i> ចូលជោគជ័យ</span>`,
    "LOGIN_FAILED": `<span class="badge-tag dropout" style="font-size: 0.76rem;"><i class="fa-solid fa-circle-xmark"></i> ចូលបរាជ័យ</span>`,
    "LOGIN_SUSPENDED": `<span class="badge-tag pending" style="font-size: 0.76rem;"><i class="fa-solid fa-ban"></i> គណនីផ្អាក</span>`,
    "LOGOUT": `<span class="badge-tag general" style="font-size: 0.76rem;"><i class="fa-solid fa-arrow-right-from-bracket"></i> ចាកចេញ</span>`
  };

  const roleBadgeMap = {
    "ADMIN": `<span class="role-tag admin" style="font-size: 0.68rem; padding: 2px 6px;">ADMIN</span>`,
    "COLLECTOR": `<span class="role-tag collector" style="font-size: 0.68rem; padding: 2px 6px;">COLLECTOR</span>`
  };

  tbody.innerHTML = filtered.map((log, idx) => {
    let dateStr = log.created_at || "";
    let formattedDate = "";
    let formattedTime = "";

    try {
      // Clean parsing of Cambodia timezone timestamp (UTC+7)
      const clean = dateStr.replace(" ", "T");
      const [dPart, tPart] = clean.split("T");
      if (dPart && tPart) {
        const [y, m, d] = dPart.split("-").map(Number);
        const [hh, mm, ss] = tPart.split(".")[0].split(":").map(Number);

        const khMonths = [
          "មករា", "កុម្ភៈ", "មីនា", "មេសា", "ឧសភា", "មិថុនា",
          "កក្កដា", "សីហា", "កញ្ញា", "តុលា", "វិច្ឆិកា", "ធ្នូ"
        ];
        const monthName = khMonths[m - 1] || m;
        formattedDate = `${d} ${monthName} ${y}`;

        let period = hh >= 12 ? "PM" : "AM";
        let h12 = hh % 12;
        if (h12 === 0) h12 = 12;
        const pad = n => String(n).padStart(2, "0");
        formattedTime = `${pad(h12)}:${pad(mm)}:${pad(ss)} ${period}`;
      } else {
        const dateObj = new Date(dateStr);
        formattedDate = `${toKhmerDigits(dateObj.getDate())} ${KHMER_MONTHS[dateObj.getMonth()]} ${toKhmerDigits(dateObj.getFullYear())}`;
        formattedTime = dateObj.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: true });
      }
    } catch (e) {
      formattedDate = dateStr;
      formattedTime = "";
    }

    let deviceText = "Browser";
    const ua = log.user_agent || "";
    if (ua.includes("Mobile") || ua.includes("Android") || ua.includes("iPhone")) {
      deviceText = "📱 ទូរស័ព្ទ (Mobile)";
    } else if (ua.includes("Windows")) {
      deviceText = "💻 កុំព្យូទ័រ (Windows PC)";
    } else if (ua.includes("Macintosh")) {
      deviceText = "💻 Mac";
    }

    return `
      <tr>
        <td class="text-center">${idx + 1}</td>
        <td style="white-space: nowrap;">
          <strong>${formattedDate}</strong>
          <small class="text-dim" style="display: block; font-size: 0.74rem; margin-top: 2px;">
            <i class="fa-regular fa-clock" style="margin-right: 4px; opacity: 0.7;"></i>${formattedTime}
          </small>
        </td>
        <td><code style="color: #60a5fa; background: rgba(37,99,235,0.1); padding: 2px 6px; border-radius: 4px; font-weight: 600;">${log.username}</code></td>
        <td>${log.full_name || '<span class="text-dim">-</span>'}</td>
        <td>${log.role ? (roleBadgeMap[log.role] || log.role) : '<span class="text-dim">-</span>'}</td>
        <td class="text-center">${actionBadgeMap[log.action] || log.action}</td>
        <td><code style="color: #cbd5e1; font-family: monospace; font-size: 0.8rem;">${log.ip_address || '127.0.0.1'}</code></td>
        <td title="${log.user_agent || ''}"><small class="text-dim">${deviceText}</small></td>
      </tr>
    `;
  }).join("");
}

// --- Authentication & Dedicated Login Form Handling ---
function showLoginScreen() {
  const overlay = document.getElementById("app-login-screen");
  if (!overlay) return;
  overlay.style.display = "flex";
  const userIn = document.getElementById("input-login-username");
  const passIn = document.getElementById("input-login-password");
  if (userIn) userIn.value = "";
  if (passIn) passIn.value = "";
  const errEl = document.getElementById("login-alert-error");
  if (errEl) errEl.style.display = "none";
  setTimeout(() => userIn?.focus(), 150);
}

function hideLoginScreen() {
  const overlay = document.getElementById("app-login-screen");
  if (overlay) overlay.style.display = "none";
}

async function handleSystemLoginSubmit(e) {
  if (e) e.preventDefault();
  const username = document.getElementById("input-login-username")?.value.trim();
  const password = document.getElementById("input-login-password")?.value;
  const submitBtn = document.getElementById("btn-login-submit");
  const errEl = document.getElementById("login-alert-error");
  const errMsgEl = document.getElementById("login-alert-msg");

  if (!username || !password) {
    if (errEl && errMsgEl) {
      errMsgEl.textContent = "សូមបំពេញឈ្មោះគណនី និងពាក្យសម្ងាត់ឱ្យបានត្រឹមត្រូវ";
      errEl.style.display = "flex";
    }
    return;
  }

  if (submitBtn) {
    submitBtn.disabled = true;
    submitBtn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> កំពុងផ្ទៀងផ្ទាត់...`;
  }
  if (errEl) errEl.style.display = "none";

  try {
    const res = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password })
    });

    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.detail || "ឈ្មោះអ្នកប្រើ ឬពាក្យសម្ងាត់មិនត្រឹមត្រូវ");
    }

    localStorage.setItem("access_token", data.access_token);
    state.currentUser = data.user_info;
    updateUserPillUI();
    hideLoginScreen();
    window.showToast(`បានចូលប្រើប្រាស់ដោយជោគជ័យ៖ ${data.user_info.full_name}`, "success");
    if (data.user_info.role === "COLLECTOR") {
      switchTab("registration");
    } else {
      window.refreshCurrentView();
    }
  } catch (err) {
    if (errEl && errMsgEl) {
      errMsgEl.textContent = err.message || "ការចូលប្រើប្រាស់បរាជ័យ";
      errEl.style.display = "flex";
    }
  } finally {
    if (submitBtn) {
      submitBtn.disabled = false;
      submitBtn.innerHTML = `<i class="fa-solid fa-right-to-bracket"></i> ចូលប្រើប្រាស់ប្រព័ន្ធ (Sign In)`;
    }
  }
}

async function handleSystemLogout() {
  if (confirm("តើលោកអ្នកពិតជាចង់ចាកចេញពីប្រព័ន្ធមែនទេ?")) {
    try {
      await apiRequest("/api/auth/logout", { method: "POST" });
    } catch (e) {
      console.warn("Logout log failed:", e);
    }
    localStorage.removeItem("access_token");
    state.currentUser = null;
    updateUserPillUI();
    showLoginScreen();
    window.showToast("បានចាកចេញពីប្រព័ន្ធដោយជោគជ័យ", "info");
  }
}

function updateUserPillUI() {
  const user = state.currentUser;
  const sidebarAvatar = document.getElementById("sidebar-avatar");
  const sidebarUsername = document.getElementById("sidebar-username");
  const menuTitle = document.getElementById("sidebar-menu-title");

  const navDashboard = document.getElementById("nav-item-dashboard");
  const navRegistration = document.getElementById("nav-item-registration");
  const navFamilies = document.getElementById("nav-item-families");
  const navGeo = document.getElementById("nav-item-geo");
  const navReports = document.getElementById("nav-item-reports");
  const navUsers = document.getElementById("nav-item-users");
  const navBackup = document.getElementById("nav-item-backup");

  if (user) {
    if (sidebarAvatar) sidebarAvatar.textContent = user.full_name ? user.full_name[0].toUpperCase() : "U";
    if (sidebarUsername) {
      sidebarUsername.innerHTML = `<strong>${user.full_name}</strong> <span class="role-tag ${user.role.toLowerCase()}" style="margin-left: 4px; font-size: 0.68rem; padding: 2px 6px;">${user.role}</span>`;
    }

    if (user.role === "ADMIN") {
      // ADMIN: Show all 7 navigation tabs
      if (menuTitle) menuTitle.innerHTML = `<i class="fa-solid fa-layer-group"></i> មុខងារចម្បងទាំង ៧`;
      if (navDashboard) navDashboard.style.display = "flex";
      if (navRegistration) navRegistration.style.display = "flex";
      if (navFamilies) navFamilies.style.display = "flex";
      if (navGeo) navGeo.style.display = "flex";
      if (navReports) navReports.style.display = "flex";
      if (navUsers) navUsers.style.display = "flex";
      if (navBackup) navBackup.style.display = "flex";
    } else {
      // COLLECTOR (អ្នកស្រង់ទិន្នន័យ): Show 'ចុះឈ្មោះគ្រួសារ' and 'បញ្ជីគ្រួសារ និងពិនិត្យ'
      if (menuTitle) menuTitle.innerHTML = `<i class="fa-solid fa-user-pen"></i> មុខងារអ្នកស្រង់ទិន្នន័យ (Collector)`;
      if (navDashboard) navDashboard.style.display = "none";
      if (navRegistration) navRegistration.style.display = "flex";
      if (navFamilies) navFamilies.style.display = "flex";
      if (navGeo) navGeo.style.display = "none";
      if (navReports) navReports.style.display = "none";
      if (navUsers) navUsers.style.display = "none";
      if (navBackup) navBackup.style.display = "none";

      if (state.currentTab !== "registration" && state.currentTab !== "families") {
        switchTab("registration");
      }
    }
  } else {
    if (sidebarAvatar) sidebarAvatar.innerHTML = `<i class="fa-solid fa-user"></i>`;
    if (sidebarUsername) sidebarUsername.textContent = "មិនទាន់ចូលប្រើ (Guest)";
    if (menuTitle) menuTitle.innerHTML = `<i class="fa-solid fa-layer-group"></i> មុខងារចម្បងទាំង ៧`;
    if (navDashboard) navDashboard.style.display = "flex";
    if (navRegistration) navRegistration.style.display = "flex";
    if (navFamilies) navFamilies.style.display = "flex";
    if (navGeo) navGeo.style.display = "flex";
    if (navReports) navReports.style.display = "flex";
    if (navUsers) navUsers.style.display = "none";
    if (navBackup) navBackup.style.display = "none";
  }
}

// Check logged in user on start
async function checkAuthSession() {
  const token = localStorage.getItem("access_token");
  if (token) {
    try {
      const res = await apiRequest("/api/auth/me");
      if (res.ok) {
        state.currentUser = await res.json();
        updateUserPillUI();
        hideLoginScreen();
        if (state.currentUser.role === "COLLECTOR") {
          if (state.currentTab !== "registration" && state.currentTab !== "families") {
            switchTab("registration");
          }
        }
        return true;
      }
    } catch (e) {
      console.warn("Invalid token or session expired");
    }
  }
  // No active session -> require login
  localStorage.removeItem("access_token");
  state.currentUser = null;
  updateUserPillUI();
  showLoginScreen();
  return false;
}

// --- App Initialization ---
document.addEventListener("DOMContentLoaded", async () => {
  // Setup Nav Tabs
  document.querySelectorAll(".nav-item").forEach(item => {
    item.addEventListener("click", (e) => {
      e.preventDefault();
      const tab = item.getAttribute("data-tab");
      switchTab(tab);
    });
  });

  // Setup Dynamic Member row trigger
  document.getElementById("btn-add-member-row")?.addEventListener("click", () => {
    addMemberRow();
  });

  // Setup Family Form Submit
  document.getElementById("form-register-family")?.addEventListener("submit", handleFamilyFormSubmit);

  // Setup Sync Button
  document.getElementById("btn-manual-sync")?.addEventListener("click", () => {
    window.syncManager.syncNow();
  });

  // Filter list search & input debounce
  document.getElementById("filter-list-search")?.addEventListener("input", () => {
    state.familiesCurrentPage = 1;
    loadFamiliesList();
  });
  document.getElementById("filter-list-poor")?.addEventListener("change", () => {
    state.familiesCurrentPage = 1;
    loadFamiliesList();
  });
  document.getElementById("filter-list-status")?.addEventListener("change", () => {
    state.familiesCurrentPage = 1;
    loadFamiliesList();
  });

  // Global Modal Closers and Triggers Delegation
  document.addEventListener("click", (e) => {
    const closeBtn = e.target.closest(".modal-close");
    if (closeBtn) {
      closeBtn.closest(".modal-backdrop")?.classList.remove("active");
      return;
    }
    if (e.target.classList && e.target.classList.contains("modal-backdrop")) {
      e.target.classList.remove("active");
      return;
    }
    if (e.target.closest(".btn-trigger-register-modal")) {
      e.preventDefault();
      window.openRegistrationModal();
      return;
    }
  });

  // User Management triggers
  document.getElementById("btn-open-create-user-modal")?.addEventListener("click", () => {
    openCreateUserModal();
  });
  document.getElementById("form-user-manage")?.addEventListener("submit", handleUserFormSubmit);
  document.getElementById("filter-user-search")?.addEventListener("input", () => renderUsersTable());
  document.getElementById("filter-user-role")?.addEventListener("change", () => renderUsersTable());

  // User Management Sub-tabs: Accounts vs Access Logs
  const subBtnUsers = document.getElementById("subtab-btn-users");
  const subBtnLogs = document.getElementById("subtab-btn-logs");
  const subPanelUsers = document.getElementById("subpanel-users");
  const subPanelLogs = document.getElementById("subpanel-logs");

  if (subBtnUsers && subBtnLogs && subPanelUsers && subPanelLogs) {
    subBtnUsers.addEventListener("click", () => {
      subBtnUsers.classList.add("btn-primary");
      subBtnUsers.classList.remove("btn-outline");
      subBtnLogs.classList.add("btn-outline");
      subBtnLogs.classList.remove("btn-primary");

      subPanelUsers.style.display = "block";
      subPanelLogs.style.display = "none";
      loadUsersList();
    });

    subBtnLogs.addEventListener("click", () => {
      subBtnLogs.classList.add("btn-primary");
      subBtnLogs.classList.remove("btn-outline");
      subBtnUsers.classList.add("btn-outline");
      subBtnUsers.classList.remove("btn-primary");

      subPanelLogs.style.display = "block";
      subPanelUsers.style.display = "none";
      loadUserLogs();
    });
  }

  // Audit Logs search and filters
  document.getElementById("filter-log-search")?.addEventListener("input", () => renderLogsTable());
  document.getElementById("filter-log-action")?.addEventListener("change", () => renderLogsTable());
  document.getElementById("btn-refresh-logs")?.addEventListener("click", () => loadUserLogs());

  // Single Member Form Submit & Real-time DOB calculation
  document.getElementById("form-single-member")?.addEventListener("submit", handleSingleMemberFormSubmit);
  
  // Edit Family Form Submit
  document.getElementById("form-edit-family")?.addEventListener("submit", handleEditFamilyFormSubmit);
  
  const smDob = document.getElementById("single-member-dob");
  const smAgeDisplay = document.getElementById("single-member-age-display");
  if (smDob && smAgeDisplay) {
    const updateSmAge = () => {
      smAgeDisplay.textContent = calculateAgeFromDob(smDob.value);
    };
    smDob.addEventListener("input", updateSmAge);
    smDob.addEventListener("change", updateSmAge);
  }

  const smDropout = document.getElementById("single-member-dropout");
  const smGrade = document.getElementById("single-member-grade");
  if (smDropout && smGrade) {
    smDropout.addEventListener("change", (e) => {
      if (e.target.value === "DROPOUT") {
        smGrade.placeholder = "ថ្នាក់បោះបង់ (លេខឡាតាំង ឧ. 7)";
      } else {
        smGrade.placeholder = "ថ្នាក់កំពុងរៀន (លេខឡាតាំង ឧ. 5)";
      }
    });
  }

  const smGradeInput = document.getElementById("single-member-grade");
  if (smGradeInput) {
    smGradeInput.addEventListener("input", (e) => {
      e.target.value = e.target.value.replace(/[^0-9]/g, "");
    });
  }

  const smBc = document.getElementById("single-member-birthcert");
  if (smBc) {
    smBc.addEventListener("input", (e) => {
      e.target.value = e.target.value.replace(/[^0-9]/g, "");
    });
    smBc.addEventListener("blur", (e) => {
      if (!e.target.value.trim()) e.target.value = "0";
    });
  }

  // Login Form Submission
  document.getElementById("form-system-login")?.addEventListener("submit", handleSystemLoginSubmit);

  // Toggle Login Password Visibility
  const togglePwdBtn = document.getElementById("btn-toggle-login-pwd");
  const pwdInput = document.getElementById("input-login-password");
  if (togglePwdBtn && pwdInput) {
    togglePwdBtn.addEventListener("click", () => {
      const isPwd = pwdInput.getAttribute("type") === "password";
      pwdInput.setAttribute("type", isPwd ? "text" : "password");
      togglePwdBtn.innerHTML = isPwd ? `<i class="fa-solid fa-eye-slash"></i>` : `<i class="fa-solid fa-eye"></i>`;
    });
  }

  // Logout Buttons
  document.getElementById("btn-topbar-logout")?.addEventListener("click", handleSystemLogout);
  document.getElementById("btn-sidebar-logout")?.addEventListener("click", handleSystemLogout);

  // Start sequence
  setupGeoCascade();
  await loadGeographicHierarchy();
  await checkAuthSession();
  await window.syncManager.updateUI();

  // Initialize first member row in form
  resetRegistrationForm();

  // Mobile Sidebar Toggle
  document.getElementById("btn-sidebar-toggle")?.addEventListener("click", () => {
    document.getElementById("app-sidebar")?.classList.toggle("open");
  });

  // Display Current Date in Khmer in Topbar
  const dateEl = document.getElementById("current-date-text");
  if (dateEl) {
    dateEl.textContent = formatKhmerFullDate(new Date());
  }

  // Setup Backup & Restore handlers
  setupBackupRestoreUI();

  // Load Dashboard by default
  loadDashboardStats();
});

// --- Database Backup & Restore Module ---
let selectedRestoreFile = null;

async function loadBackupStats() {
  const badgeText = document.getElementById("backup-engine-text");
  const statFam = document.getElementById("stat-families-count");
  const statMem = document.getElementById("stat-members-count");
  const statGeo = document.getElementById("stat-geo-count");
  const statUsers = document.getElementById("stat-users-count");
  const statLogs = document.getElementById("stat-logs-count");

  try {
    const res = await apiRequest("/api/backup/stats");
    if (!res.ok) throw new Error("Failed to fetch backup stats");
    const data = await res.json();

    if (badgeText) badgeText.textContent = data.engine;
    if (statFam) statFam.textContent = `${toKhmerDigits(data.counts.families)} គ្រួសារ`;
    if (statMem) statMem.textContent = `${toKhmerDigits(data.counts.members)} នាក់`;
    const totalGeo = data.counts.provinces + data.counts.districts + data.counts.communes + data.counts.villages;
    if (statGeo) statGeo.textContent = `${toKhmerDigits(totalGeo)} ទីតាំង`;
    if (statUsers) statUsers.textContent = `${toKhmerDigits(data.counts.users)} គណនី`;
    if (statLogs) statLogs.textContent = `${toKhmerDigits(data.counts.user_audit_logs)} កំណត់ត្រា`;
  } catch (err) {
    console.error("Backup stats error:", err);
    if (badgeText) badgeText.textContent = "មិនអាចភ្ជាប់បាន";
  }
}

async function downloadBackupSnapshot() {
  const btn = document.getElementById("btn-export-backup");
  if (!btn) return;
  const origHtml = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> កំពុងទាញយកទិន្នន័យ...`;

  try {
    const token = localStorage.getItem("access_token");
    const res = await fetch("/api/backup/export", {
      headers: token ? { "Authorization": `Bearer ${token}` } : {}
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "បរាជ័យក្នុងការទាញយក Backup");
    }

    const blob = await res.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    const now = new Date();
    const pad = n => String(n).padStart(2, "0");
    const timestamp = `${now.getFullYear()}-${pad(now.getMonth()+1)}-${pad(now.getDate())}_${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`;
    a.download = `census_backup_${timestamp}.json`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.URL.revokeObjectURL(url);

    window.showToast("ទាញយកឯកសារ Backup បានជោគជ័យ!", "success");
  } catch (err) {
    window.showToast(err.message, "error");
  } finally {
    btn.disabled = false;
    btn.innerHTML = origHtml;
  }
}

function setupBackupRestoreUI() {
  const dropZone = document.getElementById("drop-zone-backup");
  const fileInput = document.getElementById("input-restore-file");
  const fileLabel = document.getElementById("restore-file-label");
  const btnRestore = document.getElementById("btn-execute-restore");
  const btnExport = document.getElementById("btn-export-backup");

  btnExport?.addEventListener("click", downloadBackupSnapshot);

  dropZone?.addEventListener("click", () => fileInput?.click());

  dropZone?.addEventListener("dragover", (e) => {
    e.preventDefault();
    dropZone.style.borderColor = "#3b82f6";
    dropZone.style.background = "rgba(59, 130, 246, 0.1)";
  });

  dropZone?.addEventListener("dragleave", () => {
    dropZone.style.borderColor = "rgba(255, 255, 255, 0.18)";
    dropZone.style.background = "rgba(0, 0, 0, 0.2)";
  });

  dropZone?.addEventListener("drop", (e) => {
    e.preventDefault();
    dropZone.style.borderColor = "rgba(255, 255, 255, 0.18)";
    dropZone.style.background = "rgba(0, 0, 0, 0.2)";
    if (e.dataTransfer.files.length > 0) {
      handleSelectedBackupFile(e.dataTransfer.files[0]);
    }
  });

  fileInput?.addEventListener("change", (e) => {
    if (e.target.files.length > 0) {
      handleSelectedBackupFile(e.target.files[0]);
    }
  });

  function handleSelectedBackupFile(file) {
    if (!file.name.endsWith(".json")) {
      window.showToast("សូមជ្រើសរើសឯកសារទម្រង់ .json ប៉ុណ្ណោះ", "error");
      return;
    }
    selectedRestoreFile = file;
    const sizeKb = (file.size / 1024).toFixed(1);
    if (fileLabel) {
      fileLabel.innerHTML = `<strong style="color: #34d399;"><i class="fa-solid fa-file-check"></i> ${file.name}</strong> (${sizeKb} KB)`;
    }
    if (btnRestore) {
      btnRestore.disabled = false;
    }
  }

  btnRestore?.addEventListener("click", async () => {
    if (!selectedRestoreFile) return;

    const confirmed = confirm(
      "⚠️ ការព្រមានសំខាន់៖ ការស្តារទិន្នន័យឡើងវិញ នឹងជំនួសទិន្នន័យចាស់ទាំងអស់នៅក្នុងប្រព័ន្ធ។\n\nតើអ្នកពិតជាចង់បន្តដំណើរការស្តារទិន្នន័យ (Restore) មែនទេ?"
    );
    if (!confirmed) return;

    btnRestore.disabled = true;
    const origHtml = btnRestore.innerHTML;
    btnRestore.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> កំពុងស្តារទិន្នន័យ...`;

    try {
      const formData = new FormData();
      formData.append("file", selectedRestoreFile);

      const token = localStorage.getItem("access_token");
      const res = await fetch("/api/backup/restore", {
        method: "POST",
        headers: token ? { "Authorization": `Bearer ${token}` } : {},
        body: formData
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "បរាជ័យក្នុងការស្តារទិន្នន័យ");
      }

      const result = await res.json();
      window.showToast(result.message || "ស្តារទិន្នន័យបានជោគជ័យ ១០០%!", "success");

      // Reset file selection
      selectedRestoreFile = null;
      if (fileInput) fileInput.value = "";
      if (fileLabel) fileLabel.innerHTML = "ចុចទីនេះ ឬទម្លាក់ File .json ដើម្បីជ្រើសរើស";
      btnRestore.disabled = true;

      // Reload stats and current view
      loadBackupStats();
      loadDashboardStats();
      loadFamiliesList();
    } catch (err) {
      window.showToast(err.message, "error");
    } finally {
      btnRestore.innerHTML = origHtml;
    }
  });
}
