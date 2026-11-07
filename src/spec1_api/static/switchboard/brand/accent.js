// Board settings from the URL:
//   ?accent=3FB6A8  sets the accent color
//   ?paused=1       freezes every animation (the gallery's Pause button sets this)
(function () {
  var params = new URLSearchParams(location.search);
  var hex = params.get("accent");
  if (hex && /^#?[0-9a-f]{6}$/i.test(hex)) {
    document.documentElement.style.setProperty("--accent", "#" + hex.replace("#", ""));
  }
  if (params.get("paused") === "1") {
    var style = document.createElement("style");
    style.textContent = "*, *::before, *::after { animation-play-state: paused !important; }";
    document.head.appendChild(style);
  }
})();
