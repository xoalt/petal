# UX and accessibility decisions

The review follows GNOME's [design principles](https://developer.gnome.org/hig/principles.html), [keyboard guidance](https://developer.gnome.org/hig/guidelines/keyboard.html), and [accessibility guidance](https://developer.gnome.org/hig/guidelines/accessibility.html). Petal retains its custom radial wheel; it does not claim complete GNOME HIG compliance or certified accessibility.

## Feedback and empty states

An enabled leaf must respond. With no file, a leaf click shows “Select or drag a file” and briefly shakes only the clicked leaf. The center opens the file picker. Keyboard activation gives the same feedback; reduced motion disables the shake. File selection does not immediately start a conversion. Cancellation restores the previous wheel. Processing uses separate progress and Activity feedback, with a visible route to software checks when an engine is missing.

## Keyboard and pointer

Shift, Alt, and Control latch wheel modes; arrow keys navigate and Enter applies. The explicitly opened wheel takes focus while visible, releases it when hidden, and uses capture-phase handlers so GTK mnemonics cannot swallow mode changes. Passive drag previews avoid exclusive keyboard focus and observe modifiers in drag events. This does not install a global keyboard hook or change compositor bindings.

The canvas exposes a descriptive accessible name and current-action description. Right-click/Menu/Shift+F10 offers the same page's actions as named native GTK buttons. Ctrl+O opens files. Escape closes a popup before dismissing the wheel. Left and right modifier variants, held modifiers, and no-key-event drag-state changes are tested.

## Visibility and layout

Primary settings buttons calculate black/white text contrast for the chosen accent; palette tests check at least 4.5:1 contrast. Disabled controls and keyboard focus have distinct styles. Wheel colors remain configurable because wallpaper and transparency affect perceived contrast. Reduced motion respects both the app preference and GTK's animation setting.

Window defaults are capped to available logical monitor dimensions. Setup, settings, software, and editor bodies scroll, retaining footer controls. A native large-text check captures setup at a compact window size and verifies the Finish button stays inside the window.

## User choice

Program dropdowns start unselected and include an external-program picker. Nothing is marked recommended. Choosing a program is separate from confirming a reviewed download. Incompatible external engines leave the active choice unchanged. Missing engines explain affected features, and errors offer manual options instead of forced repair.

## Scope of verification

Native controls, roles, layout bounds, callback behavior, actual GTK screenshots, and layer-shell keyboard modes are tested. Full Orca/screen-reader, on-screen keyboard, every desktop portal, and every compositor are not certified by these checks. See the release verification record for measured coverage.

## Interactive work in Beta 2

Conversion and tool leaves open an editor before export. Preview generation cancels stale work; Apply stays disabled while the displayed settings are pending or invalid. Rectangle handles and coordinate fields update each other. Video geometry uses even pixel boundaries. Numeric fields provide a keyboard alternative to pointer handles. PDF page-order buttons and the text field share the same order; batch controls change the actual export order.

Completion feedback stays open with Open results, Edit result, and Done. A result can become the input for another tool. Media and combined-file previews are explicitly bounded samples, not promises of a complete timeline preview. See the editor guide for details.
