/*
 * Host test of installer/source/stats/report.c: the install id and the JSON report the app
 * sends to stats/ (whose src/event.ts accepts exactly these field names and limits).
 *
 *     report_test
 */
#include <stdio.h>
#include <string.h>

#include "../source/stats/report.h"

static int failures;

static void expect(int ok, const char *what)
{
    printf("%s  %s\n", ok ? "ok  " : "FAIL", what);
    failures += !ok;
}

static void expect_json(const Report *r, const char *want, const char *what)
{
    char out[REPORT_MAX + 1];
    size_t n = report_json(r, out, sizeof(out));
    int ok = n == strlen(want) && !strcmp(out, want);
    expect(ok, what);
    if (!ok)
        printf("      got  %s\n      want %s\n", out, want);
}

int main(void)
{
    char id[REPORT_ID_LEN + 1], shown[REPORT_ID_LEN + 2];
    report_id_encode((const uint8_t[5]){0, 0, 0, 0, 0}, id);
    expect(!strcmp(id, "00000000"), "id: zero bits");
    report_id_encode((const uint8_t[5]){0xFF, 0xFF, 0xFF, 0xFF, 0xFF}, id);
    expect(!strcmp(id, "ZZZZZZZZ"), "id: all bits");
    report_id_encode((const uint8_t[5]){0x9C, 0xF5, 0x44, 0x9F, 0xAD}, id);
    expect(report_id_valid(id) && !strpbrk(id, "ILOU"), "id: valid, no I L O U");
    report_id_display("K7QM29XD", shown);
    expect(!strcmp(shown, "K7QM-29XD"), "id: shown with a dash");
    expect(!report_id_valid("K7QM29XO") && !report_id_valid("k7qm29xd") && !report_id_valid("K7QM29X") &&
               !report_id_valid(NULL),
           "id: malformed ones refused");

    Report update = {
        .id = "K7QM29XD", .event = "update", .app = "2.0.0", .prev = "1.12.0", .model = "New Nintendo 3DS XL",
        .system = "11.17.0-50E", .luma = "13.4", .region = "EUR", .slot = "ru", .glyphs = "real", .font = "ok",
        .ms = 66900, .code = -1, .log = "files=273 moved=152 \"quoted\" back\\slash\nnext",
    };
    expect_json(&update,
                "{\"v\":1,\"id\":\"K7QM29XD\",\"event\":\"update\",\"app\":\"2.0.0\",\"prev\":\"1.12.0\","
                "\"model\":\"New Nintendo 3DS XL\",\"system\":\"11.17.0-50E\",\"luma\":\"13.4\",\"region\":\"EUR\","
                "\"slot\":\"ru\",\"glyphs\":\"real\",\"font\":\"ok\",\"ms\":66900,"
                "\"log\":\"files=273 moved=152 \\\"quoted\\\" back\\\\slash\\nnext\"}",
                "json: an update, escapes");

    Report error = {.id = "K7QM29XD", .event = "error", .app = "2.0.0", .ms = -1, .stage = "files", .code = 2,
                    .detail = "write failed\tтаб"};
    expect_json(&error,
                "{\"v\":1,\"id\":\"K7QM29XD\",\"event\":\"error\",\"app\":\"2.0.0\",\"stage\":\"files\",\"code\":2,"
                "\"detail\":\"write failed\\u0009таб\"}",
                "json: an error, optional fields left out, control characters escaped");

    /* a Ukrainian log is two bytes a letter: cut to what fits in 4 KB, never mid-letter */
    char long_log[4200] = "";
    for (int i = 0; i < 2040; i++) /* under 2048 letters, over 4 KB */
        strcat(long_log, "ї");
    Report big = {.id = "K7QM29XD", .event = "install", .app = "2.0.0", .ms = -1, .code = -1, .log = long_log};
    char out[REPORT_MAX + 1];
    size_t n = report_json(&big, out, sizeof(out));
    const char *log = strstr(out, "\"log\":\"");
    size_t bytes = log ? strlen(log + 7) - 2 : 0; /* without the closing "} */
    expect(n > REPORT_MAX - 16 && n <= REPORT_MAX, "json: a long Ukrainian log fills the 4 KB and no more");
    expect(log && bytes % 2 == 0 && !strcmp(out + n - 2, "\"}"), "json: ...cut between letters, closed");

    /* an ASCII log stops at the server's 2048 characters */
    char ascii[2200];
    memset(ascii, 'a', sizeof(ascii) - 1);
    ascii[sizeof(ascii) - 1] = 0;
    big.log = ascii;
    n = report_json(&big, out, sizeof(out));
    log = strstr(out, "\"log\":\"");
    expect(log && strlen(log + 7) - 2 == REPORT_LOG_MAX, "json: an ASCII log is cut to 2048 characters");

    expect(report_json(&update, out, 40) == 0, "json: too small a buffer gives 0");

    printf(failures ? "%d failed\n" : "all passed\n", failures);
    return failures != 0;
}
