(() => {
  "use strict";

  const manifestUrl = "downloads.json";
  const fallbackReleaseUrl = "https://github.com/mattirk/arch-rogue/releases";
  const releasePath = "/mattirk/arch-rogue/releases";
  const platformLabels = {
    windows: "Windows",
    linux: "Linux",
    macos: "macOS",
    android: "Android",
  };
  const status = document.querySelector("[data-release-status]");
  const badges = new Map(
    Array.from(document.querySelectorAll("[data-platform]"), (badge) => [badge.dataset.platform, badge])
  );

  function isRecord(value) {
    return value !== null && typeof value === "object" && !Array.isArray(value);
  }

  function isSafeDownloadUrl(value) {
    if (typeof value !== "string") return false;
    try {
      const url = new URL(value);
      return url.protocol === "https:"
        && url.hostname === "github.com"
        && url.port === ""
        && url.username === ""
        && url.password === ""
        && (url.pathname === releasePath || url.pathname.startsWith(`${releasePath}/`));
    } catch (_) {
      return false;
    }
  }

  function disableBadge(badge) {
    badge.removeAttribute("href");
    badge.removeAttribute("download");
    badge.setAttribute("role", "link");
    badge.setAttribute("aria-disabled", "true");
    badge.setAttribute("tabindex", "-1");
    badge.classList.add("is-unavailable");
  }

  function linkBadge(badge, url) {
    badge.href = url;
    badge.removeAttribute("role");
    badge.removeAttribute("aria-disabled");
    badge.removeAttribute("tabindex");
    badge.classList.remove("is-unavailable");
    if (new URL(url).pathname.includes("/releases/download/")) {
      badge.setAttribute("download", "");
    } else {
      badge.removeAttribute("download");
    }
  }

  function applyManifest(manifest) {
    if (!isRecord(manifest) || manifest.schema !== 2) {
      throw new Error("Unsupported download manifest");
    }

    const assets = isRecord(manifest.assets) ? manifest.assets : {};
    badges.forEach((badge, platform) => {
      const asset = assets[platform];
      if (!isRecord(asset) || typeof asset.available !== "boolean") return;
      if (asset.available === false) {
        disableBadge(badge);
      } else if (isSafeDownloadUrl(asset.url)) {
        linkBadge(badge, asset.url);
      }
    });

    const enabledPlatforms = [];
    badges.forEach((badge, platform) => {
      if (badge.getAttribute("aria-disabled") !== "true" && isSafeDownloadUrl(badge.href)) {
        enabledPlatforms.push(platformLabels[platform] || platform);
      }
    });

    const releaseLink = document.createElement("a");
    releaseLink.href = isSafeDownloadUrl(manifest.release_url) ? manifest.release_url : fallbackReleaseUrl;
    releaseLink.rel = "noopener";
    const version = typeof manifest.version === "string" && manifest.version.trim()
      ? manifest.version.trim()
      : null;
    releaseLink.textContent = version ? `Arch Rogue v${version}` : "Latest Arch Rogue release";

    const build = typeof manifest.commit === "string" && /^[0-9a-f]{12}$/i.test(manifest.commit)
      ? ` · build ${manifest.commit}`
      : "";
    const availability = enabledPlatforms.length
      ? ` · ${enabledPlatforms.join(" and ")} available`
      : " · builds coming soon";
    status.replaceChildren("Release: ", releaseLink, build, availability);
  }

  async function loadManifest() {
    try {
      const response = await fetch(manifestUrl, { cache: "no-store", headers: { Accept: "application/json" } });
      if (!response.ok) throw new Error(`Manifest request failed (${response.status})`);
      applyManifest(await response.json());
    } catch (error) {
      console.warn("Arch Rogue download manifest unavailable; using static page fallbacks.", error);
      status.textContent = "Release details are updating. Linux and Android open the GitHub releases page.";
    }
  }

  if (status && badges.size > 0) loadManifest();
})();
