  // The Download buttons ship with a hardcoded link to a known-good
  // installer so they work with JavaScript disabled or the API
  // unreachable. This upgrades them to whatever the newest release is,
  // so publishing a release is all that's needed — no site edit.
  //
  // Deliberately the releases LIST endpoint, not /releases/latest:
  // "latest" excludes pre-releases, and every build so far is one.
  (function () {
    fetch('https://api.github.com/repos/PokerForge/pokerforge/releases')
      .then(function (r) { return r.ok ? r.json() : Promise.reject(r.status); })
      .then(function (releases) {
        var asset, release;
        for (var i = 0; i < releases.length && !asset; i++) {
          if (releases[i].draft) continue;
          for (var j = 0; j < releases[i].assets.length; j++) {
            if (/\.exe$/i.test(releases[i].assets[j].name)) {
              asset = releases[i].assets[j];
              release = releases[i];
              break;
            }
          }
        }
        if (!asset) return;
        var links = document.querySelectorAll('.js-download');
        for (var k = 0; k < links.length; k++) {
          links[k].href = asset.browser_download_url;
        }
        var meta = document.getElementById('dl-meta');
        if (meta) {
          meta.textContent = '  ·  ' + release.tag_name +
            '  ·  ' + Math.round(asset.size / 1048576) + ' MB';
        }
      })
      .catch(function () { /* keep the hardcoded link */ });
  })();
