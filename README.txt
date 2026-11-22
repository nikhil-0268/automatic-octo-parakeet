TRINGGG HOMEPAGE

Open index.html in a modern browser. No installation or build command is needed.
Keep this folder together so the stylesheet, script and images can load.

FILES
index.html    Page content and semantic markup. Edit headings and text here.
styles.css    Colors, spacing, page layout, mobile rules and accessibility styles.
app.js        Slideshow, mobile navigation and demo pickup dialog.
assets/       The two original photographs, extracted without recompression.

WHY THESE LANGUAGES
HTML describes content, CSS controls appearance and JavaScript adds behavior.
This small static page does not need React, TypeScript or a package manager.

FIXES
The native dialog contains keyboard focus, supports Escape, and restores focus.
Whitespace-only Gate IDs show a validation error.
The slideshow has a pause control, respects reduced motion on startup and changes,
and stops its timer while the browser tab is hidden.
Mobile navigation closes on selection, outside click, Escape and desktop resize.
The hero uses content-based height to reduce clipping on short screens and zoom.
Slide controls have larger hit areas and inactive images are hidden from assistive tech.

This remains a visual demo. It does not send, store or dispatch pickup requests.
The original reference file is unchanged.
