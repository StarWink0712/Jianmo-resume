# Bundled Resume Font

The editor and exported PDF use the same unmodified **Noto Sans CJK SC 2.004**
Regular and Bold OpenType files for Chinese/symbols, and **Noto Sans 2.008**
Regular/Bold/Italic/BoldItalic TrueType files for Latin text. CJK copyright 2014-2021 Adobe
(http://www.adobe.com/); the original copyright is retained in the font metadata.

Upstream release: <https://github.com/notofonts/noto-cjk/tree/Sans2.004>

- `Sans/OTF/SimplifiedChinese/NotoSansCJKsc-Regular.otf`
- `Sans/OTF/SimplifiedChinese/NotoSansCJKsc-Bold.otf`
- The original upstream root `LICENSE` is included without changes (SIL OFL 1.1).

Latin upstream is pinned to commit
`ffebf8c1ee449e544955a7e813c54f9b73848eac` in
<https://github.com/notofonts/noto-fonts>, directory `hinted/ttf/NotoSans/`.
Its original root license is retained as `NotoSans-LICENSE` (SIL OFL 1.1).
Latin font metadata retains Copyright 2015-2021/2022 Google LLC; the upstream
license includes the Noto Project Authors notice.

Exact sizes and SHA-256 values are pinned in `experiments/m1/fonts.py`.
No network or system-font lookup is needed at run time. Do not replace these
files with fonts installed on the build machine. Package the license and this
notice along with the fonts. The fonts may be bundled/embedded under the OFL;
they may not be sold on their own. PDF recipients need no font installation.

Chinese Markdown italics use a fixed synthetic slant because the CJK family has
no italic faces; Latin uses real italic faces. Dedicated Latin files preserve
distinct Unicode mappings for ASCII hyphen and non-breaking hyphen, which share
a glyph in the CJK font. Arrows/math symbols use the bundled CJK files.
This is a redistributable sans-serif alternative, not Apple's proprietary
PingFang SC or Avenir Next. Browser antialiasing can differ between platforms;
font file identity does not guarantee pixel-identical browser rasterization.

The six files total 35,692,628 bytes. They deliberately remain unmodified fonts
for shared use by XeTeX and the browser, rather than shipping separate subsets.
