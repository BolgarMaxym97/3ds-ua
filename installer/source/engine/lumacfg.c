#include "lumacfg.h"

#include <string.h>

/* config_version_major.minor the edit was checked against: Luma3DS v13.4 writes 3.13. */
static const char *const KNOWN_MINOR[] = {"13"};

typedef struct {
    const char *s;
    size_t len;
} Span;

static Span trim(const char *s, size_t len)
{
    while (len && (*s == ' ' || *s == '\t'))
        s++, len--;
    while (len && (s[len - 1] == ' ' || s[len - 1] == '\t' || s[len - 1] == '\r'))
        len--;
    return (Span){s, len};
}

static bool eq(Span a, const char *word)
{
    return a.len == strlen(word) && !memcmp(a.s, word, a.len);
}

int lumacfg_parse(LumaConfig *c, char *text, size_t len)
{
    memset(c, 0, sizeof(*c));
    int game = 0, external = 0, major = 0, minor = 0;
    Span section = {"", 0};
    size_t pos = 0;
    while (pos < len) {
        char *s = text + pos;
        char *nl = memchr(s, '\n', len - pos);
        size_t n = nl ? (size_t)(nl - s) : len - pos;
        pos += n + 1;
        Span line = trim(s, n);
        if (!line.len || line.s[0] == ';' || line.s[0] == '#')
            continue;
        if (line.s[0] == '[') {
            if (line.s[line.len - 1] != ']')
                return -1;
            section = trim(line.s + 1, line.len - 2);
            continue;
        }
        const char *equals = memchr(line.s, '=', line.len);
        if (!equals)
            return -1;
        Span key = trim(line.s, (size_t)(equals - line.s));
        Span value = trim(equals + 1, line.len - (size_t)(equals - line.s) - 1);
        if (eq(section, "meta") && eq(key, "config_version_major")) {
            if (!eq(value, "3"))
                return -1;
            major++;
        } else if (eq(section, "meta") && eq(key, "config_version_minor")) {
            bool known = false;
            for (size_t i = 0; i < sizeof(KNOWN_MINOR) / sizeof(*KNOWN_MINOR); i++)
                known |= eq(value, KNOWN_MINOR[i]);
            if (!known)
                return -1;
            minor++;
        } else if (eq(section, "boot") && (eq(key, "enable_game_patching") || eq(key, "enable_external_firm_and_modules"))) {
            if (value.len != 1 || (value.s[0] != '0' && value.s[0] != '1'))
                return -1;
            char *at = text + (value.s - text);
            if (eq(key, "enable_game_patching"))
                c->game = at, game++;
            else
                c->external = at, external++;
        }
    }
    return major == 1 && minor == 1 && game == 1 && external == 1 ? 0 : -1;
}
