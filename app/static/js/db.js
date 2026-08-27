/**
 * IndexedDB Wrapper for Cambodia Population Census (Offline Support)
 */
const DB_NAME = "CambodiaCensusDB";
const DB_VERSION = 1;

class CensusDB {
  constructor() {
    this.db = null;
  }

  async open() {
    if (this.db) return this.db;

    return new Promise((resolve, reject) => {
      const request = indexedDB.open(DB_NAME, DB_VERSION);

      request.onupgradeneeded = (event) => {
        const db = event.target.result;
        
        // Store for pending offline families & members
        if (!db.objectStoreNames.contains("pending_families")) {
          const store = db.createObjectStore("pending_families", {
            keyPath: "offline_client_id"
          });
          store.createIndex("created_at", "created_at", { unique: false });
        }

        // Store for offline cached geographic hierarchy
        if (!db.objectStoreNames.contains("cached_geo")) {
          db.createObjectStore("cached_geo", { keyPath: "key" });
        }
      };

      request.onsuccess = (event) => {
        this.db = event.target.result;
        resolve(this.db);
      };

      request.onerror = (event) => {
        console.error("IndexedDB error:", event.target.error);
        reject(event.target.error);
      };
    });
  }

  async savePendingFamily(familyData) {
    const db = await this.open();
    return new Promise((resolve, reject) => {
      const tx = db.transaction("pending_families", "readwrite");
      const store = tx.objectStore("pending_families");
      if (!familyData.offline_client_id) {
        familyData.offline_client_id = "off_" + Date.now() + "_" + Math.random().toString(36).substr(2, 9);
      }
      familyData.created_at = new Date().toISOString();
      const request = store.put(familyData);
      request.onsuccess = () => resolve(familyData);
      request.onerror = (e) => reject(e.target.error);
    });
  }

  async getPendingFamilies() {
    const db = await this.open();
    return new Promise((resolve, reject) => {
      const tx = db.transaction("pending_families", "readonly");
      const store = tx.objectStore("pending_families");
      const request = store.getAll();
      request.onsuccess = () => resolve(request.result || []);
      request.onerror = (e) => reject(e.target.error);
    });
  }

  async deletePendingFamily(offlineClientId) {
    const db = await this.open();
    return new Promise((resolve, reject) => {
      const tx = db.transaction("pending_families", "readwrite");
      const store = tx.objectStore("pending_families");
      const request = store.delete(offlineClientId);
      request.onsuccess = () => resolve(true);
      request.onerror = (e) => reject(e.target.error);
    });
  }

  async clearPendingFamilies() {
    const db = await this.open();
    return new Promise((resolve, reject) => {
      const tx = db.transaction("pending_families", "readwrite");
      const store = tx.objectStore("pending_families");
      const request = store.clear();
      request.onsuccess = () => resolve(true);
      request.onerror = (e) => reject(e.target.error);
    });
  }

  async saveCachedGeo(geoData) {
    const db = await this.open();
    return new Promise((resolve, reject) => {
      const tx = db.transaction("cached_geo", "readwrite");
      const store = tx.objectStore("cached_geo");
      const request = store.put({ key: "hierarchy_tree", data: geoData, updated_at: new Date().toISOString() });
      request.onsuccess = () => resolve(true);
      request.onerror = (e) => reject(e.target.error);
    });
  }

  async getCachedGeo() {
    const db = await this.open();
    return new Promise((resolve, reject) => {
      const tx = db.transaction("cached_geo", "readonly");
      const store = tx.objectStore("cached_geo");
      const request = store.get("hierarchy_tree");
      request.onsuccess = () => resolve(request.result ? request.result.data : null);
      request.onerror = (e) => reject(e.target.error);
    });
  }
}

window.censusDB = new CensusDB();
