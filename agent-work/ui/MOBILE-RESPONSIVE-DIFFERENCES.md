# Desktop and mobile layout differences

This note records the responsive behavior of RAFAC Questions. The desktop layout remains the reference for wide screens; phone-specific presentation applies at widths of `680px` and below. The medium-width labelled navigation rail remains in use between the phone and desktop layouts.

## Shared application shell

| Area | Desktop | Mobile |
| --- | --- | --- |
| Navigation | Persistent labelled left rail; content sits beside it. | Rail becomes a right-side drawer below the top site header over a dimmed page. Its menu button stays in the header and scrolls with it rather than floating in the screen corner. |
| Header | Compact product header aligned to the content area. | Full-width header row with product identity and a 44px menu button; feedback messages wrap onto their own row. The drawer/backdrop start below the actual header height. The board header stays sticky while scrolling. |
| Content | Centered, capped content width with generous side spacing. | Fluid content with phone-safe gutters and safe-area padding; long words and user-provided question text wrap instead of widening the page. |
| Controls | Standard form sizing and mouse/keyboard interaction. | Inputs and selects use at least 44px height and 16px text, buttons have larger touch targets, and dialogs scroll within the visible viewport above the on-screen keyboard. |
| Scrolling | Normal document scrolling, except the question board's fixed-height workspace. | Normal document scrolling for every view, including the question board; no page-level horizontal scroll is intended. |

## Page differences

| Page or workflow | Desktop | Mobile |
| --- | --- | --- |
| Log in and change password | Standard stacked form in the centered content area. | Full-width stacked form controls with phone-sized inputs and buttons. |
| Squadron quiz and solo practice | Topic filter, progress, question card, and actions use the available width; quiz controls may wrap. | Topic and progress form a compact, readable grid; question card uses flexible height; Correct/Incorrect/Skip remain in two columns, with reveal/finish spanning the row. |
| Submit a question | Stacked form, with the normal desktop content width. | Same workflow in a single fluid column with larger fields and wrapped text. |
| Progress, sessions, practice results | Statistics may arrange across the available width; topic/session details use accordions. | Statistics use two columns; accordions and long details wrap within the page width and remain touch-friendly. |
| Review, reports, and question lists | List actions can sit beside each other and wrap as needed. | Lists stay one column; action buttons wrap with larger targets and question/answer text remains readable. |
| Admin accounts | Account form and user list use desktop spacing. | Account fields and user actions use full-width or wrapped layouts with larger controls. |
| Admin question board | Fixed-height workspace alongside the navigation rail. Six columns scroll horizontally; cards can be dragged between columns or into the editor. | Normal page flow below a sticky header. The five state columns are full-width horizontally swipeable pages with scroll snapping; swipes work from the card list as well as the column header. Collapsed cards show only question and answer; tapping expands one card across the board to show topic and Edit, Move, and Delete actions. Each page has an Add question button. Add/edit opens a centered overlay card with Save and Cancel controls. The Manage questions disclosure becomes a plain topic/bank controls card. CSV import and the drag-only Delete column are hidden on mobile. |
| Board management forms | Add, import, and topic management can appear side by side. | Forms stack in one column; destructive controls remain grouped with topic management. |

## Touch and accessibility behavior

- The phone navigation retains its existing accessible name, expanded state, Escape-to-close behavior, and backdrop close action.
- On the question board, touch users swipe between status pages from anywhere in a column and tap a card to reveal its actions. They can edit, move, delete, and add questions without drag gestures. The existing move confirmations remain in effect, and moving a reported question to another state resolves its open reports.
- Add/edit uses a centered mobile overlay card with Save and Cancel controls. The editor can save edits to the current state or save and move to another state. Reported remains available as a destination only when editing a card that is already reported. Each status page's Add question button defaults the new question to that status, except the Reported page, which defaults it to Active. The mobile Manage questions disclosure is removed; topic rename and bank clear remain available in a static card. CSV import is unavailable on mobile.
- Desktop retains its labelled rail, fixed-height question board, horizontal board columns, drag interactions, and compact board/editor typography.
- Responsive behavior is implemented in `static/style.css`; the menu button lives in the shared header in `static/index.html`; explicit mobile board actions are built in `static/app-admin.js`.
