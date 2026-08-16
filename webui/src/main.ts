/**
 * Which of the two views this document is.
 *
 * `?view=print-preview` mounts the print view alone; anything else mounts the report page,
 * which carries its own off-screen print view for the browser's Ctrl-P. One bundle, two
 * roots, and no router: there are exactly two entry points and a routing library would be a
 * dependency for a single `if`.
 *
 * The preview URL is a transient entry point, not a shareable link -- it has no report of its
 * own and asks the window that opened it for one. See `print/channel.ts`.
 *
 * Stylesheets are imported here rather than in components so that the cascade order is a
 * property of this file and not of Vite's module graph: tokens first, then the two view
 * stylesheets, which do not overlap. Both are loaded in both views -- the preview needs the
 * screen's base typography for its toolbar, and the report window needs the print rules for
 * the off-screen host.
 */
import { createApp } from 'vue'
import ScreenApp from './screen/ScreenApp.vue'
import PrintPreview from './print/PrintPreview.vue'
import { isPreviewWindow } from './print/channel'
import './tokens.css'
import './screen/screen.css'
import './print/print.css'

createApp(isPreviewWindow() ? PrintPreview : ScreenApp).mount('#app')
