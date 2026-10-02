export function effectiveStyle(style, config) {
  const result = style.version >= 2 ? structuredClone(style) : {
    ...structuredClone(config.defaults), content_size_px: style.font_size_pt * 96 / 72.27,
    section_title_size_px: 12 * 96 / 72.27, line_height: style.line_height,
    section_gap_px: style.section_gap_pt * 96 / 72.27,
    margins_px: Object.fromEntries(Object.entries(style.margins_mm).map(([key, value]) => [key, value * 96 / 25.4]))};
  for (const [key, choices] of Object.entries(config.sizes)) {
    result[key] = [...choices].sort((a, b) => Math.abs(a - result[key]) - Math.abs(b - result[key]) || a - b)[0];
  }
  result.version = 3;
  result.line_height = config.rhythm.body_line_height;
  result.section_gap_px = Math.round(result.section_gap_px);
  result.margins_px = Object.fromEntries(Object.entries(result.margins_px).map(([key, value]) => [key, Math.round(value)]));
  return result;
}

export function normalizeHex(value) {
  const hex = value.trim().replace(/^#/, '');
  return /^[a-f\d]{6}$/i.test(hex) ? '#' + hex.toUpperCase() : null;
}

export function contentOnly(section, config) {
  return ['skills', 'awards'].includes(section.type) ||
    (section.type === 'custom' && config.award_titles.includes(section.title.trim()) &&
      !(section.entries || []).some(entry => ['role', 'start_date', 'end_date', 'ongoing', 'url'].some(key => key in entry)));
}
