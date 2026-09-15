// Screenshots on the page are scaled down to fit their column, which makes
// the numbers and labels in them unreadable -- the thing a visitor most
// wants to look at. Clicking one opens it full size.
//
// Progressive enhancement: with JavaScript off the images still render
// inline exactly as before, just without the zoom.
(function () {
  var shots = document.querySelectorAll('.shot img');
  if (!shots.length) return;

  var overlay = document.createElement('div');
  overlay.className = 'lightbox';
  overlay.hidden = true;
  overlay.setAttribute('role', 'dialog');
  overlay.setAttribute('aria-modal', 'true');
  overlay.innerHTML =
    '<button class="lightbox-close" type="button" aria-label="Close">&times;</button>' +
    '<img alt="">';
  document.body.appendChild(overlay);

  var full = overlay.querySelector('img');
  var closeBtn = overlay.querySelector('.lightbox-close');
  var lastFocused = null;

  function open(img) {
    lastFocused = document.activeElement;
    full.src = img.currentSrc || img.src;
    full.alt = img.alt;
    overlay.hidden = false;
    document.body.style.overflow = 'hidden';
    closeBtn.focus();
  }

  function close() {
    overlay.hidden = true;
    full.removeAttribute('src');
    document.body.style.overflow = '';
    if (lastFocused) lastFocused.focus();
  }

  for (var i = 0; i < shots.length; i++) {
    (function (img) {
      img.tabIndex = 0;
      img.setAttribute('role', 'button');
      img.title = 'Click to enlarge';
      img.addEventListener('click', function () { open(img); });
      img.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open(img); }
      });
    })(shots[i]);
  }

  // Anywhere on the backdrop closes, including the image itself: at full
  // size there's nothing left to click it for.
  overlay.addEventListener('click', close);
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && !overlay.hidden) close();
  });
})();
