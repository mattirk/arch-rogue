(() => {
  "use strict";

  const manifestUrl = "downloads.json";
  const status = document.querySelector("[data-release-status]");
  const badges = new Map(
    Array.from(document.querySelectorAll("[data-platform]"), (badge) => [badge.dataset.platform, badge])
  );


  function isSafeDownloadUrl(value) {
    try {
      const url = new URL(value);
      return url.protocol === "https:" && url.hostname === "github.com";
    } catch (_) {
      return false;
    }
  }

  function applyManifest(manifest) {
    if (!manifest || manifest.schema !== 1 || typeof manifest.assets !== "object") {
      throw new Error("Unsupported download manifest");
    }
    let linked = 0;
    badges.forEach((badge, platform) => {
      const url = manifest.assets[platform];
      if (isSafeDownloadUrl(url)) {
        badge.href = url;
        badge.setAttribute("download", "");
        linked += 1;
      }
    });
    if (linked !== badges.size) throw new Error("Incomplete download manifest");

    const releaseLink = document.createElement("a");
    releaseLink.href = isSafeDownloadUrl(manifest.release_url) ? manifest.release_url : "https://github.com/mattirk/arch-rogue/releases";
    releaseLink.rel = "noopener";
    releaseLink.textContent = `Arch Rogue v${manifest.version}`;
    status.replaceChildren("Downloads ready: ", releaseLink, ` · build ${manifest.commit}`);
  }

  async function loadManifest() {
    try {
      const response = await fetch(manifestUrl, { cache: "no-store", headers: { Accept: "application/json" } });
      if (!response.ok) throw new Error(`Manifest request failed (${response.status})`);
      applyManifest(await response.json());
    } catch (error) {
      console.warn("Arch Rogue download manifest unavailable; using releases-page fallbacks.", error);
      status.textContent = "Direct links are updating. The buttons currently open all GitHub releases.";
    }
  }

  loadManifest();
})();
