/**
 * Synchronization Manager for Offline-First Census
 */
class SyncManager {
  constructor() {
    this.isOnline = navigator.onLine;
    this.syncing = false;
    this.initListeners();
  }

  initListeners() {
    window.addEventListener("online", () => {
      this.isOnline = true;
      this.updateUI();
      this.autoSync();
    });

    window.addEventListener("offline", () => {
      this.isOnline = false;
      this.updateUI();
    });
  }

  async updateUI() {
    const badge = document.getElementById("network-status-badge");
    const syncCountEl = document.getElementById("sync-count-badge");
    const syncBtn = document.getElementById("btn-manual-sync");

    const pending = await window.censusDB.getPendingFamilies();
    const count = pending.length;

    if (badge) {
      if (this.isOnline) {
        badge.className = "status-badge online";
        badge.innerHTML = `<span class="dot"></span> Online (ភ្ជាប់អ៊ីនធឺណិត)`;
      } else {
        badge.className = "status-badge offline";
        badge.innerHTML = `<span class="dot"></span> Offline (ក្រៅបណ្តាញ)`;
      }
    }

    if (syncCountEl) {
      syncCountEl.textContent = count;
      syncCountEl.style.display = count > 0 ? "inline-flex" : "none";
    }

    if (syncBtn) {
      syncBtn.disabled = this.syncing || !this.isOnline || count === 0;
    }
  }

  async autoSync() {
    const pending = await window.censusDB.getPendingFamilies();
    if (pending.length > 0 && this.isOnline && !this.syncing) {
      console.log(`[Sync] Auto-syncing ${pending.length} pending families...`);
      await this.syncNow();
    }
  }

  async syncNow() {
    if (this.syncing || !this.isOnline) return;
    this.syncing = true;
    const syncBtn = document.getElementById("btn-manual-sync");
    if (syncBtn) {
      syncBtn.disabled = true;
      syncBtn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> កំពុង Sync...`;
    }

    try {
      const pending = await window.censusDB.getPendingFamilies();
      if (pending.length === 0) {
        window.showToast("គ្មានទិន្នន័យត្រូវ Sync ទេ", "info");
        return;
      }

      // Generate or get client identifier
      let clientId = localStorage.getItem("census_device_id");
      if (!clientId) {
        clientId = "dev_" + Math.random().toString(36).substr(2, 9);
        localStorage.setItem("census_device_id", clientId);
      }

      const payload = {
        client_id: clientId,
        families: pending.map(f => ({
          village_id: f.village_id,
          poor_category: f.poor_category,
          address_note: f.address_note,
          status: f.status || "PENDING_REVIEW",
          offline_client_id: f.offline_client_id,
          members: f.members
        }))
      };

      const token = sessionStorage.getItem("access_token");
      const headers = { "Content-Type": "application/json" };
      if (token) {
        headers["Authorization"] = `Bearer ${token}`;
      }

      const res = await fetch("/api/sync/batch", {
        method: "POST",
        headers,
        body: JSON.stringify(payload)
      });

      if (!res.ok) {
        throw new Error("Server error during sync");
      }

      const data = await res.json();
      await window.censusDB.clearPendingFamilies();
      
      window.showToast(`ធ្វើសមកាលកម្មជោគជ័យ! (${data.synced_count} គ្រួសារ, ${data.synced_members_count} សមាជិក)`, "success");
      
      // Refresh current active view if in list or dashboard
      if (window.refreshCurrentView) {
        window.refreshCurrentView();
      }
    } catch (err) {
      console.error("[Sync Error]", err);
      window.showToast("ការ Sync មិនជោគជ័យ សូមព្យាយាមម្តងទៀត", "error");
    } finally {
      this.syncing = false;
      if (syncBtn) {
        syncBtn.innerHTML = `<i class="fa-solid fa-cloud-arrow-up"></i> ធ្វើសមកាលកម្ម (<span id="sync-count-badge">0</span>)`;
      }
      this.updateUI();
    }
  }
}

window.syncManager = new SyncManager();
