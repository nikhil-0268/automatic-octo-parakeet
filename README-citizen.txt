TRINGGG: CITIZEN WEBSITE (homepage + citizen dashboard)

HOW TO ADD: unzip into the repo ROOT (folder with index.html). Replace files when asked.
UPDATED: index.html, app.js, styles.css (homepage popup now makes real requests, "My Dashboard" link)
NEW:     js/api.js            shared data layer (citizen + collector both use it)
         resident/dashboard.html / .css / .js   citizen dashboard
         .gitignore
Citizen dashboard: request Green/Red/Both pickup, live status
(waiting -> collector on the way -> collected), Green Points, 8-pickup streak, NPR 400 -> 320 bill.
Opening resident/dashboard.html?gate=KTM-W10-0042 fills the Gate ID automatically (used by QR codes).
Demo Gate IDs: KTM-W10-0042, KTM-W10-0104, KTM-W10-0105, KTM-W01-0007, KTM-W01-0012
