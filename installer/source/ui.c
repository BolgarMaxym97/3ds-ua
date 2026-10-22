#include "ui.h"

#include <math.h>
#include <string.h>

/* romfs:/gfx/nunito_*.bcfnt: Nunito (OFL) at 700 and 800, made by `make installer` at this em size. */
#define FONT_EM 24.0f
#define LINE_HEIGHT 1.32f
/* Nunito's line box has more room above the letters than below: drawn at its top, text sits
 * high next to the icons it labels. Measured on an Old 3DS. */
#define TEXT_NUDGE 1.5f
#define TEXT_BUF_GLYPHS 4096

static C2D_Font fonts[2];
static C2D_TextBuf text_buf;
/* Measuring parses text too; a buffer of its own, emptied per call, keeps word wrap from
 * eating the frame's buffer one trial line at a time. */
static C2D_TextBuf measure_buf;

bool ui_init(void)
{
    fonts[FONT_BOLD] = C2D_FontLoad("romfs:/gfx/nunito_700.bcfnt");
    fonts[FONT_HEAVY] = C2D_FontLoad("romfs:/gfx/nunito_800.bcfnt");
    text_buf = C2D_TextBufNew(TEXT_BUF_GLYPHS);
    measure_buf = C2D_TextBufNew(512);
    return fonts[FONT_BOLD] && fonts[FONT_HEAVY] && text_buf && measure_buf;
}

void ui_exit(void)
{
    C2D_TextBufDelete(text_buf);
    C2D_TextBufDelete(measure_buf);
    C2D_FontFree(fonts[FONT_BOLD]);
    C2D_FontFree(fonts[FONT_HEAVY]);
}

void ui_frame_begin(void)
{
    C2D_TextBufClear(text_buf);
}

/* ---------------------------------------------------------------- text */

static bool parse(C2D_Text *text, FontWeight weight, const char *str)
{
    if (!C2D_TextFontParse(text, fonts[weight], text_buf, str))
        return false;
    C2D_TextOptimize(text);
    return true;
}

float ui_text_width(float px, FontWeight weight, const char *str)
{
    C2D_Text text;
    float w = 0, h = 0, s = px / FONT_EM;
    C2D_TextBufClear(measure_buf);
    if (C2D_TextFontParse(&text, fonts[weight], measure_buf, str))
        C2D_TextGetDimensions(&text, s, s, &w, &h);
    return w;
}

float ui_text(float x, float y, float px, FontWeight weight, u32 color, const char *str)
{
    C2D_Text text;
    float w = 0, h = 0, s = px / FONT_EM;
    if (!parse(&text, weight, str))
        return 0;
    C2D_TextGetDimensions(&text, s, s, &w, &h);
    C2D_DrawText(&text, C2D_WithColor, x, y + TEXT_NUDGE * px / 12, 0.5f, s, s, color);
    return w;
}

float ui_text_center(float cx, float y, float px, FontWeight weight, u32 color, const char *str)
{
    float w = ui_text_width(px, weight, str);
    return ui_text(cx - w / 2, y, px, weight, color, str);
}

float ui_text_right(float rx, float y, float px, FontWeight weight, u32 color, const char *str)
{
    float w = ui_text_width(px, weight, str);
    return ui_text(rx - w, y, px, weight, color, str);
}

/* Greedy word wrap on spaces and '\n', measured with the font itself; draws only if `draw`. */
static float wrap(float x, float y, float width, float px, FontWeight weight, u32 color, const char *str, bool draw)
{
    char line[256], trial[256];
    size_t line_len = 0;
    float line_h = px * LINE_HEIGHT, cy = y;
    const char *p = str;
    line[0] = 0;
    while (*p) {
        const char *end = p;
        while (*end && *end != ' ' && *end != '\n')
            end++;
        size_t word = (size_t)(end - p);
        if (line_len + word + 2 >= sizeof(trial))
            word = sizeof(trial) - line_len - 2;
        memcpy(trial, line, line_len);
        size_t t = line_len;
        if (line_len)
            trial[t++] = ' ';
        memcpy(trial + t, p, word);
        trial[t + word] = 0;
        if (line_len && ui_text_width(px, weight, trial) > width) {
            if (draw)
                ui_text(x, cy, px, weight, color, line);
            cy += line_h;
            memcpy(line, p, word);
            line_len = word;
        } else {
            memcpy(line, trial, t + word + 1);
            line_len = t + word;
        }
        line[line_len] = 0;
        if (*end == '\n') {
            if (draw)
                ui_text(x, cy, px, weight, color, line);
            cy += line_h;
            line_len = 0;
            line[0] = 0;
        }
        p = *end ? end + 1 : end;
    }
    if (line_len) {
        if (draw)
                ui_text(x, cy, px, weight, color, line);
        cy += line_h;
    }
    return cy - y;
}

float ui_text_wrap(float x, float y, float width, float px, FontWeight weight, u32 color, const char *str)
{
    return wrap(x, y, width, px, weight, color, str, true);
}

float ui_text_wrap_height(float width, float px, FontWeight weight, const char *str)
{
    return wrap(0, 0, width, px, weight, 0, str, false);
}

/* ---------------------------------------------------------------- shapes */

void ui_rect(float x, float y, float w, float h, u32 color)
{
    C2D_DrawRectSolid(x, y, 0.3f, w, h, color);
}

void ui_circle(float cx, float cy, float r, u32 color)
{
    C2D_DrawCircleSolid(cx, cy, 0.3f, r, color);
}

void ui_rrect(float x, float y, float w, float h, float r, u32 color)
{
    if (r * 2 > w)
        r = w / 2;
    if (r * 2 > h)
        r = h / 2;
    ui_rect(x + r, y, w - 2 * r, h, color);
    ui_rect(x, y + r, r, h - 2 * r, color);
    ui_rect(x + w - r, y + r, r, h - 2 * r, color);
    ui_circle(x + r, y + r, r, color);
    ui_circle(x + w - r, y + r, r, color);
    ui_circle(x + r, y + h - r, r, color);
    ui_circle(x + w - r, y + h - r, r, color);
}

/* A one-pixel outline plus the shadow below: a white card on the light ground needs both to
 * stay visible at every viewing angle of the TN panels. */
void ui_card(float x, float y, float w, float h, float r, u32 color, float shadow)
{
    ui_rrect(x - 1, y - 1, w + 2, h + 2 + shadow, r + 1, COL_CARD_SHADOW);
    ui_rrect(x, y, w, h, r, color);
}

void ui_ring(float cx, float cy, float r_out, float r_in, float fraction, u32 color, u32 track)
{
    const int segments = 72;
    for (int pass = 0; pass < 2; pass++) {
        float upto = pass == 0 ? 1.0f : fraction;
        u32 c = pass == 0 ? track : color;
        int n = (int)ceilf(segments * upto);
        for (int i = 0; i < n; i++) {
            float a0 = -M_PI / 2 + 2 * M_PI * i / segments;
            float a1 = -M_PI / 2 + 2 * M_PI * fminf((i + 1.0f) / segments, upto);
            float x0o = cx + cosf(a0) * r_out, y0o = cy + sinf(a0) * r_out;
            float x1o = cx + cosf(a1) * r_out, y1o = cy + sinf(a1) * r_out;
            float x0i = cx + cosf(a0) * r_in, y0i = cy + sinf(a0) * r_in;
            float x1i = cx + cosf(a1) * r_in, y1i = cy + sinf(a1) * r_in;
            C2D_DrawTriangle(x0o, y0o, c, x1o, y1o, c, x0i, y0i, c, 0.3f);
            C2D_DrawTriangle(x1o, y1o, c, x1i, y1i, c, x0i, y0i, c, 0.3f);
        }
    }
}

/* ---------------------------------------------------------------- icons */

/* Icons are drawn on a 24-unit grid, like the mock-up's stroke SVGs. */
typedef struct {
    float x, y, k, thick;
    u32 color;
} Pen;

static void line(const Pen *p, float x0, float y0, float x1, float y1)
{
    C2D_DrawLine(p->x + x0 * p->k, p->y + y0 * p->k, p->color, p->x + x1 * p->k, p->y + y1 * p->k, p->color, p->thick, 0.4f);
    C2D_DrawCircleSolid(p->x + x0 * p->k, p->y + y0 * p->k, 0.4f, p->thick / 2, p->color);
    C2D_DrawCircleSolid(p->x + x1 * p->k, p->y + y1 * p->k, 0.4f, p->thick / 2, p->color);
}

static void poly(const Pen *p, const float *pts, int n, bool closed)
{
    for (int i = 0; i + 1 < n; i++)
        line(p, pts[2 * i], pts[2 * i + 1], pts[2 * i + 2], pts[2 * i + 3]);
    if (closed)
        line(p, pts[2 * n - 2], pts[2 * n - 1], pts[0], pts[1]);
}

static void arc(const Pen *p, float cx, float cy, float r, float from_deg, float to_deg)
{
    const int steps = 18;
    for (int i = 0; i < steps; i++) {
        float a0 = (from_deg + (to_deg - from_deg) * i / steps) * (float)M_PI / 180;
        float a1 = (from_deg + (to_deg - from_deg) * (i + 1) / steps) * (float)M_PI / 180;
        line(p, cx + cosf(a0) * r, cy + sinf(a0) * r, cx + cosf(a1) * r, cy + sinf(a1) * r);
    }
}

void ui_icon(Icon icon, float cx, float cy, float size, u32 color)
{
    Pen p = {cx - size / 2, cy - size / 2, size / 24.0f, fmaxf(1.5f, size / 11.0f), color};
    switch (icon) {
    case ICON_CHECK: {
        const float pts[] = {5, 12.5f, 10, 17, 19, 7};
        poly(&p, pts, 3, false);
        break;
    }
    case ICON_INFO:
        line(&p, 12, 10.5f, 12, 17);
        C2D_DrawCircleSolid(cx, p.y + 6.5f * p.k, 0.4f, p.thick * 0.7f, color);
        break;
    case ICON_WARN: {
        const float pts[] = {12, 3.5f, 21, 19.5f, 3, 19.5f};
        poly(&p, pts, 3, true);
        line(&p, 12, 10, 12, 13.5f);
        C2D_DrawCircleSolid(cx, p.y + 16.5f * p.k, 0.4f, p.thick * 0.6f, color);
        break;
    }
    case ICON_DOWNLOAD: {
        const float head[] = {7, 11, 12, 16, 17, 11};
        line(&p, 12, 4, 12, 15);
        poly(&p, head, 3, false);
        line(&p, 5, 20, 19, 20);
        break;
    }
    case ICON_HELP:
        arc(&p, 12, 12, 9, 0, 360);
        arc(&p, 12, 9.5f, 2.6f, 180, 400);
        line(&p, 12, 12.2f, 12, 13.5f);
        C2D_DrawCircleSolid(cx, p.y + 17 * p.k, 0.4f, p.thick * 0.6f, color);
        break;
    case ICON_LIST: {
        const float tick[] = {9, 11, 12, 14, 20, 6};
        const float frame[] = {20, 12, 20, 18, 18, 20, 6, 20, 4, 18, 4, 6, 6, 4, 15, 4};
        poly(&p, frame, 8, false);
        poly(&p, tick, 3, false);
        break;
    }
    case ICON_SWAP: {
        const float a[] = {7, 4, 3, 8, 7, 12};
        const float b[] = {17, 12, 21, 16, 17, 20};
        poly(&p, a, 3, false);
        line(&p, 3, 8, 17, 8);
        poly(&p, b, 3, false);
        line(&p, 21, 16, 7, 16);
        break;
    }
    case ICON_TRASH: {
        const float can[] = {6, 7, 7, 20, 17, 20, 18, 7};
        const float lid[] = {9, 7, 9, 4, 15, 4, 15, 7};
        line(&p, 4, 7, 20, 7);
        poly(&p, lid, 4, false);
        poly(&p, can, 4, false);
        break;
    }
    case ICON_UPDATE: {
        arc(&p, 12, 12, 8, 200, 330);
        arc(&p, 12, 12, 8, 20, 150);
        const float h1[] = {18, 3, 18, 7, 14, 7};
        const float h2[] = {6, 21, 6, 17, 10, 17};
        poly(&p, h1, 3, false);
        poly(&p, h2, 3, false);
        break;
    }
    case ICON_POWER:
        line(&p, 12, 3, 12, 12);
        arc(&p, 12, 13, 7.5f, -50, 230);
        break;
    case ICON_SHIELD: {
        const float s[] = {12, 3, 20, 6, 20, 12, 17, 18, 12, 21, 7, 18, 4, 12, 4, 6};
        const float t[] = {8.5f, 12, 11, 14.5f, 15.5f, 9.5f};
        poly(&p, s, 8, true);
        poly(&p, t, 3, false);
        break;
    }
    case ICON_TELEGRAM: {
        const float plane[] = {21, 4, 3, 11, 9, 13, 11, 19, 14, 15, 19, 19};
        poly(&p, plane, 6, true);
        line(&p, 9, 13, 17, 7);
        break;
    }
    case ICON_BATTERY: {
        const float body[] = {3, 8, 19, 8, 19, 17, 3, 17};
        poly(&p, body, 4, true);
        line(&p, 21.5f, 11, 21.5f, 14);
        break;
    }
    }
}

float ui_key_hint(float x, float y, const char *key, const char *label)
{
    float h = 17;
    float w = strlen(key) > 1 ? ui_text_width(8, FONT_HEAVY, key) + 12 : h;
    ui_rrect(x, y, w, h, h / 2, COL_INK);
    ui_text_center(x + w / 2, y + (strlen(key) > 1 ? 3.5f : 1.5f), strlen(key) > 1 ? 8 : 10, FONT_HEAVY, COL_WHITE, key);
    return w + 4 + ui_text(x + w + 4, y + 1, 11, FONT_BOLD, COL_MUTED, label);
}

void ui_flag(float x, float y, float size)
{
    float r = size / 4;
    ui_rrect(x, y, size, size, r, COL_BLUE);
    ui_rrect(x, y + size / 2, size, size / 2, r, COL_YELLOW);
    ui_rect(x, y + size / 2, size, r, COL_YELLOW);
}
