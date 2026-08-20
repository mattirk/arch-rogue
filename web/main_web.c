/* Web entry driver. main() runs once at Emscripten runtime start, kicks the
 * Odin-side boot (context, runtime startup, async IndexedDB hydration), then
 * hands the frame cadence to the browser: emscripten_set_main_loop with fps=0
 * schedules the callback through requestAnimationFrame. Production builds do
 * not use ASYNCIFY; boot completion is polled from the frame callback. */
#include <emscripten.h>

extern int ar_web_boot(void);
extern int ar_web_tick(void);

static void ar_web_frame(void) {
    if (!ar_web_tick()) {
        emscripten_cancel_main_loop();
    }
}

int main(void) {
    ar_web_boot();
    emscripten_set_main_loop(ar_web_frame, 0, 1);
    return 0;
}
