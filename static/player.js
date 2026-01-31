(() => {
  function clamp(n, a, b) {
    return Math.max(a, Math.min(b, n));
  }

  function isEditable(el) {
    if (!el) return false;
    const tag = (el.tagName || "").toLowerCase();
    return tag === "input" || tag === "textarea" || el.isContentEditable;
  }

  function requestFs(el) {
    if (!el) return;
    const fn = el.requestFullscreen || el.webkitRequestFullscreen || el.mozRequestFullScreen || el.msRequestFullscreen;
    if (fn) fn.call(el);
  }

  function exitFs() {
    const fn = document.exitFullscreen || document.webkitExitFullscreen || document.mozCancelFullScreen || document.msExitFullscreen;
    if (fn) fn.call(document);
  }

  function isFs() {
    return !!(document.fullscreenElement || document.webkitFullscreenElement || document.mozFullScreenElement || document.msFullscreenElement);
  }

  function buildControls(host, videoEl) {
    // Minimal inline styling so you don't need to change CSS.
    const bar = document.createElement("div");
    bar.setAttribute("data-mytube-controls", "1");
    bar.style.display = "flex";
    bar.style.gap = ".5rem";
    bar.style.alignItems = "center";
    bar.style.justifyContent = "space-between";
    bar.style.marginTop = ".5rem";
    bar.style.flexWrap = "wrap";

    const left = document.createElement("div");
    left.style.display = "flex";
    left.style.gap = ".5rem";
    left.style.alignItems = "center";
    left.style.flexWrap = "wrap";

    const right = document.createElement("div");
    right.style.display = "flex";
    right.style.gap = ".5rem";
    right.style.alignItems = "center";
    right.style.flexWrap = "wrap";

    function mkBtn(text, title, onClick) {
      const b = document.createElement("button");
      b.type = "button";
      b.textContent = text;
      b.title = title || "";
      // try to match your existing styles
      b.className = "btn-secondary";
      b.addEventListener("click", onClick);
      return b;
    }

    const btnPlay = mkBtn("⏯", "Play/Pause (Space)", () => {
      if (!videoEl) return;
      if (videoEl.paused) videoEl.play();
      else videoEl.pause();
    });

    const btnBack = mkBtn("⏪ 10s", "Back 10s (←)", () => {
      if (!videoEl) return;
      videoEl.currentTime = Math.max(0, videoEl.currentTime - 10);
    });

    const btnFwd = mkBtn("10s ⏩", "Forward 10s (→)", () => {
      if (!videoEl) return;
      videoEl.currentTime = Math.min(videoEl.duration || (videoEl.currentTime + 10), videoEl.currentTime + 10);
    });

    const btnMute = mkBtn("🔇", "Mute (M)", () => {
      if (!videoEl) return;
      videoEl.muted = !videoEl.muted;
      btnMute.textContent = videoEl.muted ? "🔈" : "🔇";
    });

    const vol = document.createElement("input");
    vol.type = "range";
    vol.min = "0";
    vol.max = "1";
    vol.step = "0.01";
    vol.value = videoEl ? String(videoEl.volume ?? 1) : "1";
    vol.title = "Volume (↑/↓)";
    vol.style.width = "140px";
    vol.addEventListener("input", () => {
      if (!videoEl) return;
      videoEl.volume = clamp(parseFloat(vol.value || "1"), 0, 1);
      if (videoEl.volume > 0) videoEl.muted = false;
    });

    const btnFs = mkBtn("⛶", "Fullscreen (F)", () => {
      if (isFs()) exitFs();
      else requestFs(host);
    });

    // If we don't have a <video>, we only show fullscreen.
    if (videoEl) {
      left.appendChild(btnPlay);
      left.appendChild(btnBack);
      left.appendChild(btnFwd);
      left.appendChild(btnMute);
      left.appendChild(vol);
    } else {
      const note = document.createElement("span");
      note.style.opacity = "0.7";
      note.style.fontSize = ".9rem";
      note.textContent = "Fullscreen";
      left.appendChild(note);
    }

    right.appendChild(btnFs);

    bar.appendChild(left);
    bar.appendChild(right);
    return { bar, btnPlay, btnMute, vol };
  }

  function initWatchPlayer() {
    const host = document.querySelector("[data-mytube-player]");
    if (!host) return;

    // If reddit oEmbed injected, it might contain its own iframe.
    const videoEl = host.querySelector("video");
    const iframeEl = host.querySelector("iframe");

    // Insert controls bar just under player container (inside same parent)
    const controls = buildControls(host, videoEl || null);
    // Avoid duplicates if hot-reload etc
    if (!host.parentElement.querySelector("[data-mytube-controls]")) {
      host.parentElement.insertBefore(controls.bar, host.nextSibling);
    }

    // Keyboard shortcuts
    document.addEventListener("keydown", (e) => {
      // don't steal keys while typing
      if (isEditable(document.activeElement)) return;

      const k = (e.key || "").toLowerCase();

      if (k === "f") {
        e.preventDefault();
        if (isFs()) exitFs();
        else requestFs(host);
        return;
      }

      // Below only meaningful for <video>
      if (!videoEl) return;

      if (k === " " || k === "k") {
        e.preventDefault();
        if (videoEl.paused) videoEl.play();
        else videoEl.pause();
        return;
      }

      if (k === "m") {
        e.preventDefault();
        videoEl.muted = !videoEl.muted;
        return;
      }

      if (k === "arrowleft") {
        e.preventDefault();
        videoEl.currentTime = Math.max(0, videoEl.currentTime - 10);
        return;
      }

      if (k === "arrowright") {
        e.preventDefault();
        videoEl.currentTime = Math.min(videoEl.duration || (videoEl.currentTime + 10), videoEl.currentTime + 10);
        return;
      }

      if (k === "arrowup") {
        e.preventDefault();
        videoEl.volume = clamp((videoEl.volume ?? 1) + 0.05, 0, 1);
        if (controls && controls.vol) controls.vol.value = String(videoEl.volume);
        if (videoEl.volume > 0) videoEl.muted = false;
        return;
      }

      if (k === "arrowdown") {
        e.preventDefault();
        videoEl.volume = clamp((videoEl.volume ?? 1) - 0.05, 0, 1);
        if (controls && controls.vol) controls.vol.value = String(videoEl.volume);
        if (videoEl.volume === 0) videoEl.muted = true;
        return;
      }
    });

    // Hint: we can't control YouTube/Vimeo iframe playback due to cross-origin unless we integrate their APIs.
    // But fullscreen on the container always works.
    if (iframeEl) {
      // Make sure iframe can size nicely in fullscreen (usually your CSS already does).
      iframeEl.setAttribute("allowfullscreen", "true");
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    initWatchPlayer();
  });
})();
