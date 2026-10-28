/*
 * 3DS UA installer: installs, updates and removes the Ukrainian translation of the system,
 * from one app on the HOME Menu. Design and decisions: docs/plan/installer-app.md.
 */
#include <3ds.h>
#include <citro2d.h>
#include <citro3d.h>

#include "app.h"
#include "ui.h"

/* libctru gives a CIA half of the 64 MB application region as linear memory by default;
 * the screens need a few hundred KB of it. An install holds a file being restored (up to
 * ~25 MB for a large delta) and the font being built (~12 MB) at the same time, which ran
 * out of the 28 MB heap left over (2026-10-22). */
u32 __ctru_linear_heap_size = 8 * 1024 * 1024;

/* With only the linear size set, libctru hands everything else to the main heap. The 3dsx
 * runs as 3dsx_app, which on a New 3DS gets ~124 MB instead of the CIA's 64 MB: it asked
 * for a 115 MB heap, more than the 96 MB heap area of the address space, the kernel refused,
 * and libctru stopped in svcBreak before main (2026-10-28). Past the cap memory stays unused. */
#define HEAP_SIZE_MAX (OS_HEAP_AREA_END - OS_HEAP_AREA_BEGIN)

extern u32 __ctru_heap, __ctru_heap_size, __ctru_linear_heap;
extern char *fake_heap_start, *fake_heap_end;

/* libctru 2.7.0's own __system_allocateHeaps (weak), with the main heap capped. */
void __system_allocateHeaps(void)
{
    Handle reslimit = 0;
    if (R_FAILED(svcGetResourceLimit(&reslimit, CUR_PROCESS_HANDLE)))
        svcBreak(USERBREAK_PANIC);
    ResourceLimitType type = RESLIMIT_COMMIT;
    s64 max = 0, used = 0;
    svcGetResourceLimitLimitValues(&max, reslimit, &type, 1);
    svcGetResourceLimitCurrentValues(&used, reslimit, &type, 1);
    svcCloseHandle(reslimit);

    u32 remaining = (u32)(max - used) & ~0xFFF;
    if (__ctru_linear_heap_size > remaining)
        svcBreak(USERBREAK_PANIC);
    __ctru_heap_size = remaining - __ctru_linear_heap_size;
    if (__ctru_heap_size > HEAP_SIZE_MAX)
        __ctru_heap_size = HEAP_SIZE_MAX;

    if (R_FAILED(svcControlMemory(&__ctru_heap, OS_HEAP_AREA_BEGIN, 0, __ctru_heap_size, MEMOP_ALLOC,
                                  MEMPERM_READ | MEMPERM_WRITE)))
        svcBreak(USERBREAK_PANIC);
    if (R_FAILED(svcControlMemory(&__ctru_linear_heap, 0, 0, __ctru_linear_heap_size, MEMOP_ALLOC_LINEAR,
                                  MEMPERM_READ | MEMPERM_WRITE)))
        svcBreak(USERBREAK_PANIC);

    mappableInit(OS_MAP_AREA_BEGIN, OS_MAP_AREA_END);
    fake_heap_start = (char *)__ctru_heap;
    fake_heap_end = fake_heap_start + __ctru_heap_size;
}

int main(void)
{
    romfsInit();
    cfguInit();
    ptmuInit();
    amInit();
    gfxInitDefault();
    C3D_Init(C3D_DEFAULT_CMDBUF_SIZE);
    C2D_Init(C2D_DEFAULT_MAX_OBJECTS * 4);
    C2D_Prepare();
    C3D_RenderTarget *top = C2D_CreateScreenTarget(GFX_TOP, GFX_LEFT);
    C3D_RenderTarget *bottom = C2D_CreateScreenTarget(GFX_BOTTOM, GFX_LEFT);

    static App app;
    bool ready = ui_init();
    app_init(&app);

    bool touching = false;
    touchPosition last = {0, 0};
    while (ready && aptMainLoop() && !app.quit) {
        hidScanInput();
        Input in = {.down = hidKeysDown()};
        if (hidKeysHeld() & KEY_TOUCH) {
            hidTouchRead(&last);
            touching = true;
        } else if (touching) {
            touching = false;
            in.tapped = true;
            in.tap_x = last.px;
            in.tap_y = last.py;
        }
        app_update(&app, &in);

        ui_frame_begin();
        C3D_FrameBegin(C3D_FRAME_SYNCDRAW);
        C2D_TargetClear(top, COL_BG);
        C2D_SceneBegin(top);
        app_draw_top(&app);
        C2D_TargetClear(bottom, COL_BG);
        C2D_SceneBegin(bottom);
        app_draw_bottom(&app);
        C3D_FrameEnd(0);
    }

    app_exit(&app);
    ui_exit();
    C2D_Fini();
    C3D_Fini();
    gfxExit();
    amExit();
    ptmuExit();
    cfguExit();
    romfsExit();
    return 0;
}
