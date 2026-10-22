/*
 * rastertop800 - CUPS raster filter for the "BY P800" A4 thermal printer
 *                (USB 0483:5743, ESC/POS "GS v 0" raster, 216 bytes = 1728 dots per row).
 *
 * Build:   gcc -O2 -Wall -o rastertop800 rastertop800.c $(cups-config --cflags --libs)
 * Install: sudo install -o root -g root -m 0755 rastertop800 /usr/lib/cups/filter/rastertop800
 *
 * Input : CUPS raster (application/vnd.cups-raster), 8 bits per colour,
 *         W / SW / K / RGB / sRGB colour spaces (the PPD asks for 8-bit gray).
 * Output: ESC @ | GS v 0 bands (BAND_ROWS rows each) | ESC d n   -- once per page.
 *
 * Queue options (set in the PPD, usable as  lp -o NAME=VALUE):
 *   P800Mode      Dither | Threshold          (default Dither, Floyd-Steinberg)
 *   P800Threshold T96 | T128 | T160 | T192    (Threshold mode only, default T160)
 *   P800Offset    Center | L0 | L8 ... L48    (left offset of the page inside the 1728-dot row)
 *   P800Trim      True | False                    (drop blank rows at the bottom of the page)
 *   P800Feed      Feed0 | Feed6 | Feed24 | Feed48  (ESC d n after each page)
 */

#include <cups/cups.h>
#include <cups/raster.h>
#include <fcntl.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <unistd.h>

#define HEAD_BYTES 216
#define HEAD_DOTS (HEAD_BYTES * 8)
#define BAND_ROWS 128
#define TRIM_MARGIN_ROWS 16

static volatile sig_atomic_t cancelled = 0;

static void on_term(int sig)
{
  (void)sig;
  cancelled = 1;
}

static int opt_int(const char *val, char prefix, int dflt)
{
  if (!val)
    return dflt;
  if (prefix && *val == prefix)
    val++;
  else if (prefix)
    return dflt;
  return atoi(val);
}

static int luminance(const unsigned char *p, cups_cspace_t cs)
{
  switch (cs)
  {
    case CUPS_CSPACE_K:
      return 255 - p[0];
    case CUPS_CSPACE_RGB:
    case CUPS_CSPACE_SRGB:
      return (299 * p[0] + 587 * p[1] + 114 * p[2]) / 1000;
    default: /* W, SW */
      return p[0];
  }
}

static void put_band(const unsigned char *rows, int nrows)
{
  unsigned char hdr[8] = {0x1d, 0x76, 0x30, 0x00,
                          HEAD_BYTES & 0xff, HEAD_BYTES >> 8,
                          nrows & 0xff, nrows >> 8};
  fwrite(hdr, 1, sizeof hdr, stdout);
  fwrite(rows, 1, (size_t)nrows * HEAD_BYTES, stdout);
}

static int do_page(cups_raster_t *ras, const cups_page_header2_t *h,
                   int num_options, cups_option_t *options, int page)
{
  const char *v;
  int dither = 1, threshold = 160, trim = 1, feed = 6, offset, width, bpp;
  unsigned char *line, *page_buf;
  int *err_cur = NULL, *err_nxt = NULL;
  unsigned y, x;
  long last_ink = -1;

  v = cupsGetOption("P800Mode", num_options, options);
  if (v && !strcasecmp(v, "Threshold"))
    dither = 0;
  threshold = opt_int(cupsGetOption("P800Threshold", num_options, options), 'T', 160);
  v = cupsGetOption("P800Trim", num_options, options);
  if (v && (!strcasecmp(v, "Off") || !strcasecmp(v, "False") || !strcasecmp(v, "No")))
    trim = 0;
  feed = opt_int(cupsGetOption("P800Feed", num_options, options), 'F', 6);
  if (feed < 0) feed = 0;
  if (feed > 255) feed = 255;

  width = (int)h->cupsWidth;
  if (width > HEAD_DOTS)
  {
    fprintf(stderr, "ERROR: Page is %d dots wide; the P800 head is %d dots. "
            "Use a portrait page size or fit-to-page.\n", width, HEAD_DOTS);
    return 1;
  }

  v = cupsGetOption("P800Offset", num_options, options);
  if (!v || !strcasecmp(v, "Center"))
    offset = (HEAD_DOTS - width) / 2;
  else
    offset = opt_int(v, 'L', 0);
  if (offset < 0) offset = 0;
  if (offset + width > HEAD_DOTS) offset = HEAD_DOTS - width;

  bpp = (h->cupsColorSpace == CUPS_CSPACE_RGB || h->cupsColorSpace == CUPS_CSPACE_SRGB) ? 3 : 1;
  if (h->cupsBitsPerColor != 8 || h->cupsBytesPerLine < (unsigned)(width * bpp))
  {
    fprintf(stderr, "ERROR: Unsupported raster format (bits=%u colorspace=%d).\n",
            h->cupsBitsPerColor, (int)h->cupsColorSpace);
    return 1;
  }

  line = malloc(h->cupsBytesPerLine);
  page_buf = calloc(h->cupsHeight ? h->cupsHeight : 1, HEAD_BYTES);
  err_cur = calloc((size_t)width + 3, sizeof(int));
  err_nxt = calloc((size_t)width + 3, sizeof(int));
  if (!line || !page_buf || !err_cur || !err_nxt)
  {
    fputs("ERROR: Out of memory.\n", stderr);
    free(line); free(page_buf); free(err_cur); free(err_nxt);
    return 1;
  }

  fprintf(stderr, "INFO: Page %d: %ux%u px, offset %d, %s%s\n", page,
          h->cupsWidth, h->cupsHeight, offset,
          dither ? "dither" : "threshold", trim ? ", trim" : "");

  for (y = 0; y < h->cupsHeight && !cancelled; y++)
  {
    unsigned char *out = page_buf + (size_t)y * HEAD_BYTES;
    int row_has_ink = 0;
    int *tmp;

    if (cupsRasterReadPixels(ras, line, h->cupsBytesPerLine) != h->cupsBytesPerLine)
    {
      fputs("ERROR: Unable to read raster line.\n", stderr);
      free(line); free(page_buf); free(err_cur); free(err_nxt);
      return 1;
    }

    for (x = 0; x < (unsigned)width; x++)
    {
      int lum = luminance(line + (size_t)x * bpp, h->cupsColorSpace);
      int ink;

      if (dither)
      {
        int val = lum + err_cur[x + 1] / 16;
        int e;
        if (val < 0) val = 0;
        if (val > 255) val = 255;
        ink = val < 128;
        e = val - (ink ? 0 : 255);
        err_cur[x + 2] += e * 7;
        err_nxt[x]     += e * 3;
        err_nxt[x + 1] += e * 5;
        err_nxt[x + 2] += e * 1;
      }
      else
        ink = lum < threshold;

      if (ink)
      {
        int dot = offset + (int)x;
        out[dot >> 3] |= (unsigned char)(0x80 >> (dot & 7));
        row_has_ink = 1;
      }
    }

    if (row_has_ink)
      last_ink = (long)y;

    if (dither)
    {
      tmp = err_cur; err_cur = err_nxt; err_nxt = tmp;
      memset(err_nxt, 0, ((size_t)width + 3) * sizeof(int));
    }
  }

  if (!cancelled)
  {
    long nrows = (long)h->cupsHeight, done;

    if (trim)
    {
      nrows = last_ink < 0 ? 0 : last_ink + 1 + TRIM_MARGIN_ROWS;
      if (nrows > (long)h->cupsHeight)
        nrows = (long)h->cupsHeight;
    }

    fwrite("\x1b\x40", 1, 2, stdout);
    for (done = 0; done < nrows; done += BAND_ROWS)
    {
      int n = (nrows - done) < BAND_ROWS ? (int)(nrows - done) : BAND_ROWS;
      put_band(page_buf + (size_t)done * HEAD_BYTES, n);
    }
    {
      unsigned char tail[3] = {0x1b, 0x64, (unsigned char)feed};
      fwrite(tail, 1, 3, stdout);
    }
    fflush(stdout);
  }

  free(line); free(page_buf); free(err_cur); free(err_nxt);
  return 0;
}

int main(int argc, char *argv[])
{
  cups_raster_t *ras;
  cups_page_header2_t header;
  cups_option_t *options = NULL;
  int num_options = 0, fd = 0, page = 0, rc = 0;

  if (argc < 6 || argc > 7)
  {
    fprintf(stderr, "Usage: %s job-id user title copies options [file]\n", argv[0]);
    return 1;
  }

  signal(SIGTERM, on_term);
  num_options = cupsParseOptions(argv[5], 0, &options);

  if (argc == 7 && (fd = open(argv[6], O_RDONLY)) < 0)
  {
    perror("ERROR: Unable to open raster file");
    return 1;
  }

  ras = cupsRasterOpen(fd, CUPS_RASTER_READ);
  if (!ras)
  {
    fputs("ERROR: Unable to open raster stream.\n", stderr);
    return 1;
  }

  while (!cancelled && cupsRasterReadHeader2(ras, &header))
  {
    page++;
    fprintf(stderr, "PAGE: %d 1\n", page);
    if ((rc = do_page(ras, &header, num_options, options, page)) != 0)
      break;
  }

  cupsRasterClose(ras);
  if (fd > 0)
    close(fd);
  cupsFreeOptions(num_options, options);

  if (page == 0 && !rc)
    fputs("ERROR: No pages found.\n", stderr);
  return rc || page == 0;
}
