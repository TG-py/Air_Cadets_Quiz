# RAFAC Questions UI Design Rules

Use this guide when creating or updating user interfaces for RAFAC Questions. The goal is a calm, confident squadron-learning dashboard: aviation-inspired, practical, modern, and easy to use at a glance. Follow existing product behaviour and accessibility needs while applying these visual rules.

## 1. Design direction

- Treat the interface as a **squadron learning workspace**, not a generic quiz-game screen. Use a dashboard feel without inventing widgets or adding product features as part of a visual redesign.
- Pair RAF-inspired navy and roundel blue with warm off-white surfaces and restrained sky-blue or lime accents.
- Make the interface feel focused, capable, and welcoming. Avoid a militaristic or overly decorative look.
- Prioritize clear hierarchy, readable question text, and obvious controls. The current question and its action buttons should be the visual focus.
- Use purposeful details only: thin dividers, small uppercase labels, discreet progress indicators, and simple line-style icons.

## 2. Colour tokens

Use these as the default palette. Keep contrast strong and colour use consistent across pages.

| Token | Value | Use |
|---|---|---|
| `navy` | `#071B2D` | Main navigation rail, strong dark surfaces |
| `navy-raised` | `#0D2940` | Question feature card or raised dark panel |
| `blue` | `#1461A0` | Primary actions and key links |
| `sky` | `#7EC8E3` | Small highlights, active navigation marker |
| `cream` | `#F3F2EC` | Main application canvas |
| `surface` | `#FBFBF8` | Cards and utility panels |
| `ink` | `#102538` | Main text on light surfaces |
| `muted` | `#71808B` | Supporting text and metadata |
| `line` | `#DFE6E8` | Borders and separators |
| `lime` | `#B7DD78` | Progress fill and positive accent |
| `success-bg` | `#E5EFD9` | Correct/positive action background |
| `success-ink` | `#39563C` | Correct/positive action text |
| `danger-bg` | `#F6E2DF` | Incorrect/destructive-context action background |
| `danger-ink` | `#88413B` | Incorrect/destructive-context action text |
| `warning-bg` | `#F5EDD7` | Skip/caution action background |
| `warning-ink` | `#765F2C` | Skip/caution action text |

- Use colour to communicate meaning, not as decoration.
- Do not rely on colour alone for a state: include a label, icon, or other clear cue.
- Keep large text/background combinations at accessible contrast. Test contrast when changing tokens.
- Reserve red for incorrect or genuinely destructive/error states. Do not use it as a general accent.

## 3. Layout and page structure

### Desktop shell

- Use a two-part application shell: a persistent dark navigation rail on the left and a light content area on the right.
- Set the desktop rail near `250px` wide. At medium widths, use a labelled rail around `220px`; do not collapse it to a narrow icon strip because the current navigation has no icon-only label system.
- Keep the content area's brand header compact (around `60–70px`) and use it for the product identity. Account identity and login controls belong in the rail's session area, as in the current layout.
- Constrain primary page content to about `1000px`, centered in the available content area.
- Use generous page padding (about `38–42px` desktop, `15–24px` mobile).
- Separate sections with whitespace and restrained borders rather than nested boxes everywhere.

### Navigation

- Show the RAFAC Questions identity at the top of the rail, using the roundel as a small brand mark.
- Group destinations with small uppercase section labels, such as main navigation and administration.
- Show the current page with a darker blue selection surface and a narrow sky-blue leading marker.
- Keep badges small, legible, and attached to the relevant destination.
- Keep account identity and role near the bottom of the rail.
- Preserve the existing Learning and Administration groups and role-based visibility. Non-admin users must not see admin destinations; signed-out users must retain public practice and question-submission access.
- Keep the current-page marker, label sizes, and vertical spacing consistent across both groups.

### Responsive behaviour

- At desktop widths, use the labelled navigation rail at about `250px` wide.
- At medium widths, keep the rail labelled and reduce it to about `220px`; maintain readable navigation text.
- At phone widths (around `680px` and below), use the existing menu toggle in the top header and slide-in navigation drawer. The toggle stays part of the header rather than floating at the viewport corner.
- Stack side-by-side panels into one column on narrow screens and preserve page scrolling, safe-area padding, and readable controls when the browser chrome or keyboard changes the visible height.
- Keep answer controls easy to tap, with a two-column arrangement when needed; use comfortably sized touch targets and avoid small input text that triggers mobile browser zoom.
- Avoid page-level horizontal scrolling. Let long questions and labels wrap naturally; a contained horizontal scroller is acceptable only for data that truly needs it.
- Make desktop drag-and-drop workflows available through explicit buttons and selectors on touch screens. Keep compact desktop layouts and desktop drag interactions unchanged.
- On phone-sized admin question boards, use one horizontally swipeable status page at a time. Keep question cards compact with question and answer visible; reveal topic and actions only after a tap. Provide an Add question action on each status page and omit CSV import from the phone interface.
- Let horizontal swipes start anywhere within a phone status page, including its vertically scrollable card list. Present add/edit forms as centered overlay cards rather than content below the board; keep cancel and save actions available.
- Keep essential text readable on phones. Avoid tiny metadata styles for question content, controls, and administrative actions.

## 4. Typography

- Use **Manrope** if it is already available locally, with a system sans-serif fallback. A comparable clean sans-serif is acceptable. Do not depend on a remotely loaded font: the app's Content Security Policy restricts external styles and assets.
- Use **DM Mono** (or a system monospace fallback) sparingly for tiny metadata: eyebrow labels, codes, and compact status details.
- Use sentence case for headings and actions. Reserve uppercase for short section labels and tags.
- Main page headings: roughly `28–32px`, bold, with slightly tight letter spacing. Keep heading size, weight, spacing, and supporting-text treatment consistent across views.
- Question text: roughly `22–24px` on desktop, comfortable line-height, and high contrast against its card.
- Body text: roughly `13–15px`; supporting metadata: roughly `10–12px`, but never make essential instructions too small.
- Keep text widths comfortable. Long descriptions should not span the full viewport.

## 5. Surfaces, shape, and depth

- Use a warm off-white application canvas and near-white cards.
- Use a dark navy raised surface for the active question feature card, which should be the most visually prominent component.
- Apply one shared card padding and border treatment to forms, accordions, review lists, and summary panels. Keep the active question card prominent while retaining the shared spacing and typography system.
- Use one page-heading pattern across all views: matching heading scale, weight, top spacing, and introductory copy width.
- Give cards a subtle `1px` border and modest corner radius (about `8–12px`).
- Use shadows sparingly. Prefer border, surface contrast, and spacing to communicate grouping.
- Keep controls and tags softly rounded (about `4–8px`); avoid pill-shaped styling everywhere.
- Avoid heavy gradients, glass effects, noisy textures, and large background photography. The brand should come from the palette and structure.

## 6. Question and quiz experience

- Lead with a small context label (for example, the topic or “Squadron knowledge check”), then show the question prominently.
- Keep answer visibility explicit. When hidden, say so and provide a clear reveal action. When revealed, make the answer distinct from the question.
- Show the session progress information the app currently provides as a compact, clearly labelled count. Add a progress bar only if the interface has a real progress value and the requested work includes that component.
- Keep the topic filter and small explanatory metadata below or near the question card, not competing with the question.
- Keep **Correct**, **Incorrect**, **Skip**, **Show answer**, and session completion in the existing quiz control area. Preserve their placement and meaning during a visual redesign; do not move answer reveal into the question card unless the product layout is intentionally being changed.
- Use consistent button heights, padding, and label weight throughout the site. Keep a clear primary/secondary/destructive hierarchy; correct, incorrect, and skip retain their semantic colours and explicit labels.
- Keep the session finish action visually quieter than the answer decisions, but still easy to find.
- Provide feedback after actions and preserve clear focus/disabled/loading states.
- Do not invent session data. Use actual application data or clearly marked mock values in prototypes.

## 7. Existing pages and data

- Treat the existing HTML, JavaScript, API responses, and database-backed values as the source of truth for what each page can show.
- Do not add mock totals, recent-topic panels, charts, or other dashboard widgets to the live site unless the requested work includes the data and behavior that support them. In prototypes, label sample values clearly.
- Apply the shared shell and components to existing pages: squadron quiz, solo practice, question submission, progress, question review, question bank, quiz/practice results, staff accounts, and password changes.
- Preserve each page's existing content and workflow. Adjust its hierarchy for the task while reusing the same heading, card, field, button, and spacing patterns.
- Keep solo practice visibly distinct with its green solo label and notice. Reuse the squadron quiz's question typography, card proportions, and controls so it remains part of the same product.
- On the progress page, present only totals and per-topic/per-question details the application actually supplies. Keep summaries clear and compact.

## 8. Buttons, fields, and interaction states

- Primary actions use RAF blue with white text. Keep labels short and action-oriented.
- Secondary actions use a pale blue-grey surface or a quiet outline.
- Correct, incorrect, and skip actions use the semantic backgrounds and foregrounds in the palette table.
- Controls should have clear hover, keyboard-focus, pressed, disabled, and loading states. Focus must be visible against both light and dark surfaces.
- Use a consistent control height around `40–44px` where practical, with adequate click/tap targets.
- Inputs and selects use a near-white surface, a fine border, readable labels, and a clear focus treatment. Never use placeholder text as the only label.
- Destructive administrative actions should be visually separated from routine actions and named unambiguously.
- Keep button size, corner radius, font weight, and spacing uniform across forms, modals, lists, and quiz controls. Vary emphasis by action role, not by page.

## 9. Iconography and RAFAC identity

- Use simple, consistent line or single-colour icons. Pair icons with text for important navigation and actions.
- Use the roundel as a small identity mark, not as a repeated decoration.
- Do not recreate official insignia inaccurately or imply endorsement beyond the product's existing identity.
- Avoid emoji as interface icons in the finished UI.

## 10. Accessibility and content rules

- Preserve semantic HTML, heading order, form labels, button names, keyboard operation, and screen-reader announcements.
- Ensure all interactive elements can be reached and operated by keyboard, with a visible focus indicator.
- Respect reduced-motion preferences. Animation should be subtle and never required to understand state.
- Keep status and result messages understandable without colour or position alone.
- Use plain, concise language appropriate for cadets, NCOs, and staff.
- Distinguish solo practice from squadron sessions with an explicit label and supporting explanation; never imply solo results affect squadron totals if they do not.
- Preserve the product's role-based access and workflow. A visual redesign must not expose staff-only or admin-only controls to unauthorised users.
- Preserve existing element IDs, state classes, and `hidden` attributes used by JavaScript for navigation, role gating, dialogs, banners, and view state. CSS must not make a hidden control visible.
- Keep the quiz and practice flows behaviorally identical unless the user explicitly asks for a functional change.

## 11. Project implementation rules

- Check the current `static/index.html`, `static/style.css`, and `static/app.js` before designing. The existing markup, data, and interaction code are authoritative; the mockup is a visual reference only.
- Prefer updating existing component styles and shared tokens. Consolidate obsolete declarations when practical instead of repeatedly appending conflicting override blocks.
- Keep new styles tied to existing semantic components. Do not add markup or JavaScript behavior solely to imitate mockup-only content.
- Avoid external font, image, or stylesheet dependencies. Use project assets or local system fallbacks that work under the app's Content Security Policy.
- Keep responsive behavior consistent with the existing desktop rail, medium labelled rail, and phone drawer.

## 12. Do and avoid

### Do

- Make one obvious focal point per page.
- Reuse spacing, border, type, and colour tokens consistently.
- Use one consistent page-heading pattern, card spacing system, and button sizing across views.
- Keep navigation stable across views.
- Keep the solo-practice colour cue distinct while sharing core component layout.
- Use small details to reinforce an aviation training context while keeping the interface practical.
- Check desktop, medium, and phone layouts, keyboard focus, hidden-state behavior, and text contrast.

### Avoid

- Generic neon gamer aesthetics, camouflage, tactical HUD graphics, or distressed military textures.
- Excessive red, bright gradients, decorative glows, or giant background roundels.
- Tiny low-contrast text for essential information.
- Multiple competing primary buttons in one decision area.
- Dense dashboards that bury the question or task.
- Invented statistics, dashboard cards, or data the application does not provide.
- Page-specific button sizes, heading scales, card padding, or border styles without a clear functional reason.
- Replacing clear action words with icon-only controls.

## 13. Quick implementation checklist for AI workers

Before presenting a UI change, confirm that it:

1. Uses the RAFAC dashboard palette and light canvas/dark rail structure.
2. Gives the current page and primary task a clear visual hierarchy.
3. Reuses a consistent heading pattern, card spacing, control dimensions, and semantic action colours.
4. Keeps the labelled desktop/medium rail and phone drawer usable, with the phone menu toggle inside the header.
5. Keeps JavaScript-controlled IDs, classes, and hidden states intact.
6. Preserves existing functionality, permissions, and solo-versus-squad distinction.
7. Uses only available application data or clearly labels placeholder content in mockups.
8. Updates existing style rules cleanly and avoids growing override conflicts.
9. Gives touch users an explicit alternative for workflows that rely on dragging on desktop.
